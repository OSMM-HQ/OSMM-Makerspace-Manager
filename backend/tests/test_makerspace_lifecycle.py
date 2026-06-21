from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import (
    DatabaseError,
    InternalError,
    ProgrammingError,
    connection,
    transaction,
)
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.apiclients.models import ApiClient, ApiKeyRequest
from apps.audit.models import AuditLog
from apps.boxes.models import Box, BoxScan, QrCode, QrScanEvent
from apps.evidence.models import EvidencePhoto
from apps.hardware_requests.asset_link_models import HardwareRequestItemAsset
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem
from apps.hardware_requests.return_models import RequesterAccountability, ReturnEvent
from apps.hardware_requests.self_checkout_models import PublicToolLoan
from apps.integrations.models import EmailTemplate
from apps.inventory.models import Category, InventoryAsset, InventoryProduct
from apps.makerspaces import lifecycle
from apps.makerspaces.models import Makerspace, MakerspaceMembership
from apps.operations.models import (
    InventoryAdjustment,
    QrPrintBatch,
    QrPrintBatchItem,
    StocktakeLine,
    StocktakeSession,
    StockTransfer,
    StockTransferLine,
)
from apps.printing.models import (
    FilamentSpool,
    ManualPrintLog,
    PrintBucket,
    PrintPrinter,
    PrintRequest,
    PrintRequestFile,
)

pytestmark = pytest.mark.django_db


def make_user(username, role=User.Role.REQUESTER, **overrides):
    defaults = {
        "email": f"{username}@example.com",
        "access_status": User.AccessStatus.ACTIVE,
    }
    defaults.update(overrides)
    return User.objects.create_user(username=username, role=role, **defaults)


def make_superadmin(username="lifecycle-superadmin"):
    return make_user(
        username,
        role=User.Role.SUPERADMIN,
        is_staff=True,
        is_superuser=True,
    )


def make_space(slug, **overrides):
    defaults = {"name": slug, "slug": slug}
    defaults.update(overrides)
    return Makerspace.objects.create(**defaults)


def authenticated_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def result_ids(response):
    data = response.data
    if isinstance(data, dict) and "results" in data:
        data = data["results"]
    return {item["id"] for item in data}


def archive_space(makerspace, actor):
    return lifecycle.archive(makerspace, actor)


def test_archive_rejected_on_hidden_makerspace():
    makerspace = make_space("lifecycle-hidden", superadmin_access_enabled=False)
    actor = make_superadmin()

    with pytest.raises(ValidationError):
        lifecycle.archive(makerspace, actor)

    makerspace.refresh_from_db()
    assert makerspace.archived_at is None
    assert makerspace.archived_by is None


def test_archive_unarchive_state_and_double_archive_guard():
    makerspace = make_space("lifecycle-archive-state", public_inventory_enabled=True)
    actor = make_superadmin()

    archived = lifecycle.archive(makerspace, actor)

    archived.refresh_from_db()
    assert archived.archived_at is not None
    assert archived.archived_by == actor
    assert archived.public_inventory_enabled is False

    with pytest.raises(ValidationError):
        lifecycle.archive(archived, actor)

    unarchived = lifecycle.unarchive(archived, actor)
    unarchived.refresh_from_db()
    assert unarchived.archived_at is None
    assert unarchived.archived_by is None
    assert unarchived.public_inventory_enabled is False


def test_purge_rejected_unless_archived_enabled_and_superuser(monkeypatch):
    actor = make_superadmin("lifecycle-purge-super")
    non_superuser = make_user("lifecycle-purge-not-super")
    monkeypatch.setattr(lifecycle, "_delete_storage_keys", lambda keys: None)

    not_archived = make_space("lifecycle-purge-not-archived")
    with pytest.raises(ValidationError):
        lifecycle.purge(not_archived, actor)

    hidden = make_space("lifecycle-purge-hidden")
    archived_hidden = archive_space(hidden, actor)
    Makerspace.objects.filter(pk=archived_hidden.pk).update(superadmin_access_enabled=False)
    archived_hidden.refresh_from_db()
    with pytest.raises(ValidationError):
        lifecycle.purge(archived_hidden, actor)

    archived = archive_space(make_space("lifecycle-purge-not-superuser"), actor)
    with pytest.raises(ValidationError):
        lifecycle.purge(archived, non_superuser)


def populate_full_purge_graph(makerspace, survivor, actor):
    requester = make_user(f"requester-{makerspace.slug}")
    survivor_user = make_user(f"requester-{survivor.slug}")

    box = Box.objects.create(makerspace=makerspace, label="Lifecycle Bin")
    qr = QrCode.objects.create(
        makerspace=makerspace,
        payload=box.code,
        target_type=QrCode.TargetType.BOX,
        target_id=box.id,
        created_by=actor,
    )
    category = Category.objects.create(
        makerspace=makerspace,
        name="Lifecycle Category",
        slug="lifecycle-category",
    )
    product = InventoryProduct.objects.create(
        makerspace=makerspace,
        box=box,
        category=category,
        name="Lifecycle Product",
        description="Purge graph product",
        total_quantity=5,
        available_quantity=2,
        issued_quantity=1,
        damaged_quantity=1,
        lost_quantity=1,
        is_public=True,
    )
    asset = InventoryAsset.objects.create(
        makerspace=makerspace,
        product=product,
        box=box,
        asset_tag="LIFE-ASSET-1",
    )

    issue_photo = EvidencePhoto.objects.create(
        makerspace=makerspace,
        evidence_type=EvidencePhoto.EvidenceType.ISSUE,
        object_key=f"evidence/{makerspace.id}/issue.jpg",
        uploaded_by=actor,
    )
    return_photo = EvidencePhoto.objects.create(
        makerspace=makerspace,
        evidence_type=EvidencePhoto.EvidenceType.RETURN,
        object_key=f"evidence/{makerspace.id}/return.jpg",
        uploaded_by=actor,
    )
    hardware_request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        status=HardwareRequest.Status.ISSUED,
        assigned_box=box,
        issued_by=actor,
        issued_at=timezone.now(),
        issue_evidence=issue_photo,
    )
    request_item = HardwareRequestItem.objects.create(
        request=hardware_request,
        product=product,
        requested_quantity=1,
        accepted_quantity=1,
        issued_quantity=1,
    )
    HardwareRequestItemAsset.objects.create(request_item=request_item, asset=asset)
    BoxScan.objects.create(
        makerspace=makerspace,
        box=box,
        request=hardware_request,
        actor=actor,
        context=BoxScan.Context.ISSUE,
    )
    QrScanEvent.objects.create(
        makerspace=makerspace,
        qr_code=qr,
        request=hardware_request,
        actor=actor,
        context=QrScanEvent.Context.ISSUE,
    )
    ReturnEvent.objects.create(
        request=hardware_request,
        makerspace=makerspace,
        box=box,
        evidence=return_photo,
        remark="Returned with notes.",
        actor=actor,
    )
    RequesterAccountability.objects.create(
        requester=requester,
        request=hardware_request,
        request_item=request_item,
        makerspace=makerspace,
        issue_type=RequesterAccountability.IssueType.DAMAGED,
        description="Damaged during use.",
        evidence_photo=return_photo,
        quantity=1,
        created_by=actor,
    )
    PublicToolLoan.objects.create(
        makerspace=makerspace,
        qr_code=qr,
        container=box,
        request=hardware_request,
        requester=requester,
        target_type="product",
        target_id=product.id,
        target_label=product.name,
        asset_ids=[asset.id],
        qr_ids=[qr.id],
    )

    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Lifecycle Printer")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        color="black",
        initial_weight_grams=Decimal("1000.00"),
        remaining_weight_grams=Decimal("900.00"),
    )
    bucket = PrintBucket.objects.create(makerspace=makerspace, name="Lifecycle Bucket")
    print_request = PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Lifecycle Print",
        quantity=1,
        status=PrintRequest.Status.COMPLETED,
        printer=printer,
        filament_spool=spool,
        estimated_minutes=45,
        estimated_filament_grams=Decimal("25.00"),
        filament_grams_used=Decimal("25.00"),
        completed_at=timezone.now(),
        contact_email="print@example.com",
    )
    PrintRequestFile.objects.create(
        print_request=print_request,
        makerspace=makerspace,
        kind=PrintRequestFile.Kind.STL,
        object_key=f"printing/{makerspace.id}/model.stl",
        content_type="model/stl",
        original_filename="model.stl",
        owner_checkin_user_id="print-owner",
        attached_at=timezone.now(),
    )
    ManualPrintLog.objects.create(
        makerspace=makerspace,
        printer=printer,
        filament_spool=spool,
        grams_used=Decimal("12.50"),
        title="Walk-up print",
        logged_by=actor,
    )

    stocktake = StocktakeSession.objects.create(
        makerspace=makerspace,
        container=box,
        started_by=actor,
    )
    StocktakeLine.objects.create(
        stocktake=stocktake,
        product=product,
        container=box,
        expected_quantity=2,
        counted_quantity=1,
        variance_quantity=-1,
    )
    InventoryAdjustment.objects.create(
        makerspace=makerspace,
        stocktake=stocktake,
        product=product,
        delta_available=-1,
        reason="Lifecycle stocktake",
        created_by=actor,
    )

    qr_batch = QrPrintBatch.objects.create(
        makerspace=makerspace,
        title="Lifecycle labels",
        created_by=actor,
    )
    QrPrintBatchItem.objects.create(
        batch=qr_batch,
        qr_code=qr,
        label_text=box.label,
        target_type=qr.target_type,
        target_id=qr.target_id,
    )

    same_transfer = StockTransfer.objects.create(
        makerspace=makerspace,
        source_container=box,
        destination_container=box,
        created_by=actor,
        reason="Move inside space",
        applied_at=timezone.now(),
    )
    StockTransferLine.objects.create(
        transfer=same_transfer,
        product=product,
        quantity=1,
    )

    survivor_product = InventoryProduct.objects.create(
        makerspace=survivor,
        name="Survivor Product",
        total_quantity=1,
        available_quantity=1,
    )
    cross_transfer = StockTransfer.objects.create(
        makerspace=makerspace,
        source_makerspace=makerspace,
        destination_makerspace=survivor,
        created_by=actor,
        reason="Cross-space move",
        applied_at=timezone.now(),
    )
    StockTransferLine.objects.create(
        transfer=cross_transfer,
        product=product,
        quantity=1,
    )
    survivor_adjustment = InventoryAdjustment.objects.create(
        makerspace=survivor,
        transfer=cross_transfer,
        product=survivor_product,
        delta_available=1,
        reason="Destination receipt",
        created_by=actor,
    )

    ApiClient.objects.create(
        makerspace=makerspace,
        label="Lifecycle client",
        secret_encrypted=b"encrypted-secret",
        allowed_origins=["https://client.example.com"],
    )
    ApiKeyRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        label="Lifecycle API key",
        reason="Testing purge.",
    )
    EmailTemplate.objects.create(
        makerspace=makerspace,
        stream="hardware",
        audience="requester",
        key="request_received",
        subject="Request received",
        text_body="Received.",
    )
    MakerspaceMembership.objects.create(
        makerspace=makerspace,
        user=survivor_user,
        role=MakerspaceMembership.Role.INVENTORY_MANAGER,
    )
    AuditLog.objects.create(
        actor=actor,
        action="lifecycle.scoped",
        target_type="makerspace.Makerspace",
        target_id=str(makerspace.id),
        makerspace=makerspace,
    )

    return {
        "survivor_adjustment": survivor_adjustment,
        "cross_transfer": cross_transfer,
    }


def assert_purged_makerspace_graph(space_id):
    assert Box.objects.filter(makerspace_id=space_id).count() == 0
    assert QrCode.objects.filter(makerspace_id=space_id).count() == 0
    assert QrScanEvent.objects.filter(makerspace_id=space_id).count() == 0
    assert BoxScan.objects.filter(makerspace_id=space_id).count() == 0
    assert Category.objects.filter(makerspace_id=space_id).count() == 0
    assert InventoryProduct.objects.filter(makerspace_id=space_id).count() == 0
    assert InventoryAsset.objects.filter(makerspace_id=space_id).count() == 0
    assert HardwareRequest.objects.filter(makerspace_id=space_id).count() == 0
    assert HardwareRequestItem.objects.filter(request__makerspace_id=space_id).count() == 0
    assert HardwareRequestItemAsset.objects.filter(
        request_item__request__makerspace_id=space_id
    ).count() == 0
    assert ReturnEvent.objects.filter(makerspace_id=space_id).count() == 0
    assert RequesterAccountability.objects.filter(makerspace_id=space_id).count() == 0
    assert EvidencePhoto.objects.filter(makerspace_id=space_id).count() == 0
    assert PublicToolLoan.objects.filter(makerspace_id=space_id).count() == 0
    assert PrintBucket.objects.filter(makerspace_id=space_id).count() == 0
    assert PrintRequest.objects.filter(bucket__makerspace_id=space_id).count() == 0
    assert PrintRequestFile.objects.filter(makerspace_id=space_id).count() == 0
    assert PrintPrinter.objects.filter(makerspace_id=space_id).count() == 0
    assert FilamentSpool.objects.filter(makerspace_id=space_id).count() == 0
    assert ManualPrintLog.objects.filter(makerspace_id=space_id).count() == 0
    assert StocktakeSession.objects.filter(makerspace_id=space_id).count() == 0
    assert StocktakeLine.objects.filter(stocktake__makerspace_id=space_id).count() == 0
    assert InventoryAdjustment.objects.filter(makerspace_id=space_id).count() == 0
    assert QrPrintBatch.objects.filter(makerspace_id=space_id).count() == 0
    assert QrPrintBatchItem.objects.filter(batch__makerspace_id=space_id).count() == 0
    assert StockTransfer.objects.filter(
        makerspace_id=space_id,
    ).count() == 0
    assert StockTransfer.objects.filter(source_makerspace_id=space_id).count() == 0
    assert StockTransfer.objects.filter(destination_makerspace_id=space_id).count() == 0
    assert StockTransferLine.objects.filter(transfer__makerspace_id=space_id).count() == 0
    assert ApiClient.objects.filter(makerspace_id=space_id).count() == 0
    assert ApiKeyRequest.objects.filter(makerspace_id=space_id).count() == 0
    assert EmailTemplate.objects.filter(makerspace_id=space_id).count() == 0
    assert MakerspaceMembership.objects.filter(makerspace_id=space_id).count() == 0
    assert AuditLog.objects.filter(makerspace_id=space_id).count() == 0


@pytest.mark.django_db(transaction=True)
def test_comprehensive_purge_removes_entire_makerspace_graph_and_preserves_survivor(monkeypatch):
    actor = make_superadmin("lifecycle-drift-super")
    makerspace = make_space("lifecycle-drift")
    survivor = make_space("lifecycle-drift-survivor")
    refs = populate_full_purge_graph(makerspace, survivor, actor)
    space_id = makerspace.id
    survivor_id = survivor.id
    survivor_adjustment_id = refs["survivor_adjustment"].id
    monkeypatch.setattr(lifecycle, "_delete_storage_keys", lambda keys: None)

    archived = archive_space(makerspace, actor)
    lifecycle.purge(archived, actor)

    assert_purged_makerspace_graph(space_id)
    assert not Makerspace.objects.filter(pk=space_id).exists()
    assert Makerspace.objects.filter(pk=survivor_id).exists()

    survivor_adjustment = InventoryAdjustment.objects.get(pk=survivor_adjustment_id)
    assert survivor_adjustment.makerspace_id == survivor_id
    assert survivor_adjustment.transfer_id is None
    assert AuditLog.objects.filter(
        action="makerspace.purged",
        makerspace__isnull=True,
        meta__makerspace_id=space_id,
    ).exists()


@pytest.mark.django_db(transaction=True)
def test_comprehensive_purge_under_managed_postgres(monkeypatch):
    monkeypatch.setattr("django.conf.settings.MANAGED_POSTGRES", True)
    actor = make_superadmin("lifecycle-managed-super")
    makerspace = make_space("lifecycle-managed")
    survivor = make_space("lifecycle-managed-survivor")
    refs = populate_full_purge_graph(makerspace, survivor, actor)
    space_id = makerspace.id
    survivor_id = survivor.id
    survivor_adjustment_id = refs["survivor_adjustment"].id
    monkeypatch.setattr(lifecycle, "_delete_storage_keys", lambda keys: None)

    archived = archive_space(makerspace, actor)
    lifecycle.purge(archived, actor)

    assert_purged_makerspace_graph(space_id)
    assert not Makerspace.objects.filter(pk=space_id).exists()
    assert Makerspace.objects.filter(pk=survivor_id).exists()

    survivor_adjustment = InventoryAdjustment.objects.get(pk=survivor_adjustment_id)
    assert survivor_adjustment.makerspace_id == survivor_id
    assert survivor_adjustment.transfer_id is None
    assert AuditLog.objects.filter(
        action="makerspace.purged",
        makerspace__isnull=True,
        meta__makerspace_id=space_id,
    ).exists()


@pytest.mark.django_db(transaction=True)
def test_immutable_update_still_blocked_under_purge_guard():
    actor = make_superadmin("lifecycle-managed-update-super")
    audit_log = AuditLog.objects.create(actor=actor, action="managed.before_update")

    with pytest.raises((InternalError, ProgrammingError)):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL app.allow_immutable_delete = 'on'")
                cursor.execute(
                    "UPDATE audit_auditlog SET action = %s WHERE id = %s",
                    ["managed.mutated", audit_log.id],
                )


@pytest.mark.django_db(transaction=True)
def test_purge_reenables_immutable_triggers_for_surviving_rows(monkeypatch):
    actor = make_superadmin("lifecycle-trigger-super")
    doomed = make_space("lifecycle-trigger-doomed")
    survivor = make_space("lifecycle-trigger-survivor")
    survivor_log = AuditLog.objects.create(
        actor=actor,
        action="survivor.before_purge",
        makerspace=survivor,
    )
    monkeypatch.setattr(lifecycle, "_delete_storage_keys", lambda keys: None)

    archived = archive_space(doomed, actor)
    lifecycle.purge(archived, actor)

    AuditLog.objects.create(
        actor=actor,
        action="survivor.after_purge",
        makerspace=survivor,
    )
    assert AuditLog.objects.filter(action="survivor.after_purge").exists()

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE audit_auditlog SET action = %s WHERE id = %s",
                    ["survivor.mutated", survivor_log.id],
                )

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM audit_auditlog WHERE id = %s",
                    [survivor_log.id],
                )


@pytest.mark.django_db
def test_archived_makerspace_is_excluded_from_api_scopes(monkeypatch, settings):
    settings.API_CLIENT_AUTH_REQUIRED = False
    actor = make_superadmin("lifecycle-scope-super")
    archived_space = make_space(
        "lifecycle-scope-archived",
        public_inventory_enabled=True,
    )
    visible_space = make_space(
        "lifecycle-scope-visible",
        public_inventory_enabled=True,
    )
    archived_space.enabled_modules = ["public_inventory", "request_workflow", "printing", "reports"]
    visible_space.enabled_modules = ["public_inventory", "request_workflow", "printing", "reports"]
    archived_space.save(update_fields=["enabled_modules"])
    visible_space.save(update_fields=["enabled_modules"])

    archived_requester = make_user("lifecycle-scope-archived-requester")
    visible_requester = make_user("lifecycle-scope-visible-requester")
    archived_product = InventoryProduct.objects.create(
        makerspace=archived_space,
        name="Archived Tool",
        total_quantity=2,
        available_quantity=1,
        issued_quantity=1,
        is_public=True,
    )
    visible_product = InventoryProduct.objects.create(
        makerspace=visible_space,
        name="Visible Tool",
        total_quantity=2,
        available_quantity=1,
        issued_quantity=1,
        is_public=True,
    )
    archived_request = HardwareRequest.objects.create(
        makerspace=archived_space,
        requester=archived_requester,
        requester_username=archived_requester.username,
        status=HardwareRequest.Status.ISSUED,
        issued_at=timezone.now(),
    )
    HardwareRequestItem.objects.create(
        request=archived_request,
        product=archived_product,
        requested_quantity=1,
        issued_quantity=1,
    )
    visible_request = HardwareRequest.objects.create(
        makerspace=visible_space,
        requester=visible_requester,
        requester_username=visible_requester.username,
        status=HardwareRequest.Status.ISSUED,
        issued_at=timezone.now(),
    )
    HardwareRequestItem.objects.create(
        request=visible_request,
        product=visible_product,
        requested_quantity=1,
        issued_quantity=1,
    )

    archived_bucket = PrintBucket.objects.create(makerspace=archived_space, name="Archived Bucket")
    visible_bucket = PrintBucket.objects.create(makerspace=visible_space, name="Visible Bucket")
    archived_printer = PrintPrinter.objects.create(makerspace=archived_space, name="Archived Printer")
    visible_printer = PrintPrinter.objects.create(makerspace=visible_space, name="Visible Printer")
    archived_print = PrintRequest.objects.create(
        bucket=archived_bucket,
        requester=archived_requester,
        title="Archived Print",
        status=PrintRequest.Status.COMPLETED,
        printer=archived_printer,
        estimated_minutes=60,
        completed_at=timezone.now(),
        contact_email="archived-print@example.com",
    )
    visible_print = PrintRequest.objects.create(
        bucket=visible_bucket,
        requester=visible_requester,
        title="Visible Print",
        status=PrintRequest.Status.COMPLETED,
        printer=visible_printer,
        estimated_minutes=60,
        completed_at=timezone.now(),
        contact_email="visible-print@example.com",
    )
    AuditLog.objects.create(actor=actor, action="archived.scope", makerspace=archived_space)
    AuditLog.objects.create(actor=actor, action="visible.scope", makerspace=visible_space)

    archived = archive_space(archived_space, actor)
    client = authenticated_client(actor)
    public_client = APIClient()

    managed = client.get(
        reverse("printing:managed-request-list"),
        {"makerspace": archived.id},
    )
    assert managed.status_code in (200, 403)
    if managed.status_code == 200:
        assert result_ids(managed) == set()

    ledger = client.get(reverse("ledger-aggregate"))
    assert ledger.status_code == 200
    assert {row["makerspace_id"] for row in ledger.data["results"]} == {visible_space.id}

    summary = client.get(reverse("analytics-aggregate", kwargs={"report_key": "summary"}))
    assert summary.status_code == 200
    assert summary.data["products"] == 1
    assert summary.data["active_loans"] == 1
    assert summary.data["issued_quantity"] == 1

    printing_report = client.get(reverse("printing:admin-report"))
    assert printing_report.status_code == 200
    assert printing_report.data["totals"]["total_requests"] == 1
    assert {row["makerspace_id"] for row in printing_report.data["printer_hours"]} == {
        visible_space.id
    }

    audit_logs = client.get(
        f"{reverse('admin-audit-logs')}?makerspace={archived.id}"
    )
    assert audit_logs.status_code == 200
    assert audit_logs.data["results"] == []

    bootstrap = public_client.get(f"/api/v1/bootstrap?tenant={archived.public_code}")
    assert bootstrap.status_code == 404

    public_inventory = public_client.get(
        reverse("public-inventory", kwargs={"makerspace_slug": archived.slug})
    )
    assert public_inventory.status_code == 404

    switcher = client.get(reverse("admin-makerspaces"))
    assert switcher.status_code == 200
    assert archived.id not in {row["id"] for row in switcher.data}
    assert visible_space.id in {row["id"] for row in switcher.data}

    request_status = public_client.get(
        reverse(
            "hardware_requests:request-status",
            kwargs={"public_token": archived_request.public_token},
        )
    )
    assert request_status.status_code == 404

    print_status = public_client.get(
        reverse(
            "printing:public-request-status",
            kwargs={"public_token": archived_print.public_token},
        )
    )
    assert print_status.status_code == 404

    visible_print_status = public_client.get(
        reverse(
            "printing:public-request-status",
            kwargs={"public_token": visible_print.public_token},
        )
    )
    assert visible_print_status.status_code == 200


def test_archived_makerspace_rejects_staff_create_and_authenticated_printing(settings):
    settings.API_CLIENT_AUTH_REQUIRED = False
    actor = make_superadmin("lifecycle-archived-writes-super")
    space = make_space("lifecycle-archived-writes")
    space.enabled_modules = ["staff_admin", "printing"]
    space.save(update_fields=["enabled_modules"])
    bucket = PrintBucket.objects.create(makerspace=space, name="Bucket")

    archived = archive_space(space, actor)
    client = authenticated_client(actor)

    # Superadmin staff creation must NOT attach new staff to an archived makerspace.
    create_resp = client.post(
        reverse("admin-users-space-managers"),
        {
            "username": "archived-new-sm",
            "role": "space_manager",
            "makerspace_id": archived.id,
        },
        format="json",
    )
    assert create_resp.status_code == 400

    requester = make_user("lifecycle-archived-requester-2")
    requester_client = authenticated_client(requester)

    # Authenticated requester can no longer list buckets for an archived space...
    buckets = requester_client.get(reverse("printing:bucket-list"), {"makerspace": archived.id})
    assert buckets.status_code == 200
    assert buckets.data == []

    # ...nor create a print request against its bucket.
    create_print = requester_client.post(
        reverse("printing:request-list"),
        {"bucket": bucket.id, "title": "x", "quantity": 1},
        format="json",
    )
    assert create_print.status_code == 400
