from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.boxes.models import Box
from apps.hardware_requests.models import (
    HardwareRequest,
    HardwareRequestItem,
    HardwareRequestItemAsset,
    PublicToolLoan,
)
from apps.inventory.models import InventoryAsset, TrackingMode
from tests.return_helpers import (
    authenticated_client,
    make_member,
    make_product,
    make_return_evidence,
    make_issue_evidence,
    make_space,
    make_user,
)

pytestmark = pytest.mark.django_db

_current_direct_makerspace = None


def _request_loan(
    makerspace,
    product,
    username,
    *,
    quantity=1,
    returned=0,
    status=None,
    requester=None,
    assigned_box=None,
):
    requester = requester or make_user(username, access_status=User.AccessStatus.ACTIVE)
    issued_at = timezone.now() - timedelta(days=2)
    hardware_request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        status=status or HardwareRequest.Status.ISSUED,
        assigned_box=assigned_box,
        issued_at=issued_at,
        return_due_at=issued_at + timedelta(days=7),
    )
    HardwareRequestItem.objects.create(
        request=hardware_request,
        product=product,
        requested_quantity=quantity,
        accepted_quantity=quantity,
        issued_quantity=quantity,
        returned_quantity=returned,
    )
    return hardware_request


def _self_checkout_loan(
    makerspace,
    product,
    username,
    *,
    container=None,
    source=PublicToolLoan.Source.PUBLIC_SELF_CHECKOUT,
):
    requester = make_user(username, access_status=User.AccessStatus.ACTIVE)
    issued_at = timezone.now() - timedelta(days=1)
    hardware_request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        status=HardwareRequest.Status.ISSUED,
        issued_at=issued_at,
    )
    HardwareRequestItem.objects.create(
        request=hardware_request,
        product=product,
        requested_quantity=1,
        accepted_quantity=1,
        issued_quantity=1,
    )
    loan = PublicToolLoan.objects.create(
        makerspace=makerspace,
        request=hardware_request,
        requester=requester,
        container=container,
        target_type="product",
        target_id=product.id,
        target_label=product.name,
        status=PublicToolLoan.Status.CHECKED_OUT,
        source=source,
        due_at=issued_at + timedelta(days=3),
    )
    loan.checked_out_at = issued_at
    loan.save(update_fields=["checked_out_at"])
    return loan


def _direct_url(makerspace):
    global _current_direct_makerspace
    _current_direct_makerspace = makerspace
    return f"/api/v1/admin/makerspace/{makerspace.id}/direct-loans"


def _direct_payload(**overrides):
    payload = {
        "requester_name": "Ledger Holder",
        "contact_email": "ledger-holder@example.com",
        "contact_phone": "+15550101010",
    }
    payload.update(overrides)
    if "evidence_id" not in payload and _current_direct_makerspace_is_live():
        payload["evidence_id"] = _direct_issue_evidence().id
    return payload

def _current_direct_makerspace_is_live():
    return _current_direct_makerspace is not None and _current_direct_makerspace.__class__.objects.filter(pk=_current_direct_makerspace.pk).exists()

def _direct_issue_evidence():
    assert _current_direct_makerspace is not None
    actor = User.objects.filter(makerspace_memberships__makerspace=_current_direct_makerspace).first()
    if actor is None:
        actor = make_user(
            f"evidence-{_current_direct_makerspace.slug}",
            access_status=User.AccessStatus.ACTIVE,
        )
    return make_issue_evidence(_current_direct_makerspace, actor)

def _direct_return_url(loan):
    return f"/api/v1/admin/direct-loans/{loan.id}/return"


def _return_body(evidence, notes="Container returned."):
    return {"evidence_id": evidence.id, "notes": notes}


def test_ledger_returns_outstanding_request_and_self_checkout_scoped_to_makerspace():
    makerspace = make_space("ledger-scope-a")
    other_space = make_space("ledger-scope-b")
    manager = make_member("ledger-manager-a", makerspace)
    request_product = make_product(makerspace, name="Oscilloscope")
    self_product = make_product(makerspace, name="Logic Analyzer")
    other_product = make_product(other_space, name="Foreign Meter")
    request_loan = _request_loan(
        makerspace,
        request_product,
        "ledger-requester-a",
        quantity=3,
        returned=1,
        status=HardwareRequest.Status.PARTIALLY_RETURNED,
    )
    self_loan = _self_checkout_loan(makerspace, self_product, "ledger-self-a")
    _request_loan(other_space, other_product, "ledger-requester-b", quantity=4)

    response = authenticated_client(manager).get(f"/api/v1/admin/makerspace/{makerspace.id}/ledger")

    assert response.status_code == 200
    assert response.data["count"] == 2
    rows = {(row["source"], row["item_name"]): row for row in response.data["results"]}
    assert rows[("request", "Oscilloscope")]["quantity"] == 2
    assert rows[("request", "Oscilloscope")]["reference_id"] == request_loan.id
    assert rows[("self_checkout", "Logic Analyzer")]["quantity"] == 1
    assert rows[("self_checkout", "Logic Analyzer")]["reference_id"] == self_loan.id
    assert {row["makerspace_id"] for row in response.data["results"]} == {makerspace.id}


def test_ledger_includes_container_labels_for_reviewed_requests_and_direct_loans():
    makerspace = make_space("ledger-containers")
    manager = make_member("ledger-containers-manager", makerspace)
    reviewed_product = make_product(makerspace, name="Review Kit")
    direct_product = make_product(makerspace, name="Direct Kit")
    loose_product = make_product(makerspace, name="Loose Kit")
    reviewed_box = Box.objects.create(makerspace=makerspace, label="Reviewed Box")
    direct_box = Box.objects.create(makerspace=makerspace, label="Direct Box")
    _request_loan(
        makerspace,
        reviewed_product,
        "ledger-container-reviewed-holder",
        assigned_box=reviewed_box,
    )
    _self_checkout_loan(
        makerspace,
        direct_product,
        "ledger-container-direct-holder",
        container=direct_box,
        source=PublicToolLoan.Source.ADMIN_DIRECT,
    )
    _request_loan(makerspace, loose_product, "ledger-container-loose-holder")

    response = authenticated_client(manager).get(
        f"/api/v1/admin/makerspace/{makerspace.id}/ledger"
    )

    assert response.status_code == 200
    rows = {row["item_name"]: row for row in response.data["results"]}
    assert rows["Review Kit"]["source"] == "request"
    assert rows["Review Kit"]["container"] == "Reviewed Box"
    assert rows["Direct Kit"]["source"] == "direct_handout"
    assert rows["Direct Kit"]["container"] == "Direct Box"
    assert rows["Loose Kit"]["container"] is None


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_container_only_direct_handout_appears_once_in_ledger_and_returns(
    monkeypatch,
):
    makerspace = make_space("ledger-empty-container-api")
    manager = make_member("ledger-empty-container-manager", makerspace)
    container = Box.objects.create(makerspace=makerspace, label="Empty Travel Bin")
    client = authenticated_client(manager)

    issued = client.post(
        _direct_url(makerspace),
        _direct_payload(
            requester_name="Empty Container Holder",
            contact_email="empty-container-holder@example.com",
            container_id=container.id,
        ),
        format="json",
    )

    assert issued.status_code == 201
    loan = PublicToolLoan.objects.select_related("request", "container").get()
    assert loan.container == container
    assert loan.target_label == container.label
    assert loan.request.items.count() == 0
    assert loan.request.status == HardwareRequest.Status.ISSUED
    assert AuditLog.objects.filter(
        action="admin_direct.checked_out",
        target_type="boxes.box",
        target_id=str(container.id),
        meta__loan_id=loan.id,
        meta__request_id=loan.request_id,
        meta__container_id=container.id,
    ).exists()

    ledger = client.get(f"/api/v1/admin/makerspace/{makerspace.id}/ledger")

    assert ledger.status_code == 200
    rows = [
        row
        for row in ledger.data["results"]
        if row["item_name"] == container.label
    ]
    assert len(rows) == 1
    assert rows[0]["source"] == "direct_handout"
    assert rows[0]["quantity"] == 1
    assert rows[0]["container"] is None
    assert rows[0]["reference_id"] == loan.id

    evidence = make_return_evidence(makerspace, manager)
    monkeypatch.setattr("apps.evidence.storage.object_exists", lambda key: True)
    returned = client.post(
        _direct_return_url(loan),
        _return_body(evidence),
        format="json",
    )

    assert returned.status_code == 200
    loan.refresh_from_db()
    loan.request.refresh_from_db()
    assert loan.status == PublicToolLoan.Status.RETURNED
    assert loan.request.status == HardwareRequest.Status.RETURNED
    assert AuditLog.objects.filter(
        action="admin_direct.returned",
        target_type="boxes.box",
        target_id=str(container.id),
        meta__loan_id=loan.id,
        meta__request_id=loan.request_id,
        meta__container_id=container.id,
    ).exists()

    after_return = client.get(f"/api/v1/admin/makerspace/{makerspace.id}/ledger")

    assert after_return.status_code == 200
    assert all(
        row["item_name"] != container.label for row in after_return.data["results"]
    )


def test_loaded_direct_container_is_not_double_listed_in_ledger():
    makerspace = make_space("ledger-loaded-container")
    manager = make_member("ledger-loaded-container-manager", makerspace)
    product = make_product(makerspace, name="Loaded Kit")
    container = Box.objects.create(makerspace=makerspace, label="Loaded Bin")
    _self_checkout_loan(
        makerspace,
        product,
        "ledger-loaded-container-holder",
        container=container,
        source=PublicToolLoan.Source.ADMIN_DIRECT,
    )

    response = authenticated_client(manager).get(
        f"/api/v1/admin/makerspace/{makerspace.id}/ledger"
    )

    assert response.status_code == 200
    rows = response.data["results"]
    assert len(rows) == 1
    assert rows[0]["item_name"] == "Loaded Kit"
    assert rows[0]["source"] == "direct_handout"
    assert rows[0]["container"] == "Loaded Bin"
    assert all(row["item_name"] != "Loaded Bin" for row in rows)


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_container_only_handout_rejected_when_container_has_available_contents():
    # A container-only handout assigns an EMPTY vessel. If the box still holds available
    # contents, handing out the container alone would walk them out the door while leaving
    # them logically AVAILABLE (re-loanable) — the workflow must reject it.
    makerspace = make_space("ledger-nonempty-container")
    manager = make_member("ledger-nonempty-container-manager", makerspace)
    container = Box.objects.create(makerspace=makerspace, label="Loaded Travel Bin")
    make_product(makerspace, name="Stowed Kit", box=container)
    client = authenticated_client(manager)

    response = client.post(
        _direct_url(makerspace),
        _direct_payload(
            requester_name="Nonempty Container Holder",
            contact_email="nonempty-container-holder@example.com",
            container_id=container.id,
        ),
        format="json",
    )

    assert response.status_code == 400
    assert "Container is not empty" in str(response.data)
    assert PublicToolLoan.objects.count() == 0


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_container_only_handout_rejected_when_child_box_has_contents():
    # The empty-container guard must see contents nested in CHILD boxes, else a parent
    # container-only loan would walk the child box's available stock out untracked.
    makerspace = make_space("ledger-childbox-container")
    manager = make_member("ledger-childbox-manager", makerspace)
    parent = Box.objects.create(makerspace=makerspace, label="Parent Bin")
    child = Box.objects.create(makerspace=makerspace, label="Child Bin", parent=parent)
    make_product(makerspace, name="Nested Kit", box=child)
    client = authenticated_client(manager)

    response = client.post(
        _direct_url(makerspace),
        _direct_payload(
            requester_name="Childbox Holder",
            contact_email="childbox-holder@example.com",
            container_id=parent.id,
        ),
        format="json",
    )

    assert response.status_code == 400
    assert "Container is not empty" in str(response.data)
    assert PublicToolLoan.objects.count() == 0


def test_checked_out_container_reappears_when_loaded_items_are_resolved():
    makerspace = make_space("ledger-container-resolved-items")
    manager = make_member("ledger-container-resolved-manager", makerspace)
    product = make_product(makerspace, name="Resolved Kit")
    container = Box.objects.create(makerspace=makerspace, label="Still Out Bin")
    loan = _self_checkout_loan(
        makerspace,
        product,
        "ledger-container-resolved-holder",
        container=container,
        source=PublicToolLoan.Source.ADMIN_DIRECT,
    )
    item = loan.request.items.get()
    item.returned_quantity = item.issued_quantity
    item.save(update_fields=["returned_quantity"])
    loan.request.status = HardwareRequest.Status.PARTIALLY_RETURNED
    loan.request.save(update_fields=["status", "updated_at"])

    response = authenticated_client(manager).get(
        f"/api/v1/admin/makerspace/{makerspace.id}/ledger"
    )

    assert response.status_code == 200
    assert response.data["count"] == 1
    row = response.data["results"][0]
    assert row["item_name"] == "Still Out Bin"
    assert row["quantity"] == 1
    assert row["container"] is None
    assert row["reference_id"] == loan.id


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_direct_handout_requires_item_qr_or_container_even_after_module_gate():
    makerspace = make_space("ledger-empty-direct-guard")
    manager = make_member("ledger-empty-direct-guard-manager", makerspace)
    container = Box.objects.create(makerspace=makerspace, label="Disabled Module Bin")
    client = authenticated_client(manager)

    empty = client.post(
        _direct_url(makerspace),
        _direct_payload(contact_email="empty-direct-holder@example.com"),
        format="json",
    )

    assert empty.status_code == 400
    assert "Provide qr_payloads, items, or a container." in str(empty.data)

    makerspace.enabled_modules = [
        module for module in makerspace.enabled_modules if module != "containers"
    ]
    makerspace.save(update_fields=["enabled_modules"])
    module_disabled = client.post(
        _direct_url(makerspace),
        _direct_payload(
            contact_email="module-disabled-holder@example.com",
            container_id=container.id,
        ),
        format="json",
    )

    assert module_disabled.status_code == 400
    assert "Provide qr_payloads, items, or a container." in str(
        module_disabled.data
    )
    assert PublicToolLoan.objects.count() == 0


def test_ledger_excludes_fully_returned_loans():
    makerspace = make_space("ledger-returned")
    manager = make_member("ledger-returned-manager", makerspace)
    product = make_product(makerspace, name="Returned Drill")
    _request_loan(
        makerspace,
        product,
        "ledger-returned-holder",
        quantity=2,
        returned=2,
        status=HardwareRequest.Status.PARTIALLY_RETURNED,
    )

    response = authenticated_client(manager).get(f"/api/v1/admin/makerspace/{makerspace.id}/ledger")

    assert response.status_code == 200
    assert response.data == {"count": 0, "results": []}


def test_space_manager_cannot_read_other_makerspace_ledger_and_sees_own_rows():
    space_a = make_space("ledger-manager-a-space")
    space_b = make_space("ledger-manager-b-space")
    manager_a = make_member("ledger-manager-only-a", space_a)
    product_a = make_product(space_a, name="A Tool")
    product_b = make_product(space_b, name="B Tool")
    _request_loan(space_a, product_a, "ledger-holder-a")
    _request_loan(space_b, product_b, "ledger-holder-b")
    client = authenticated_client(manager_a)

    denied = client.get(f"/api/v1/admin/makerspace/{space_b.id}/ledger")
    allowed = client.get(f"/api/v1/admin/makerspace/{space_a.id}/ledger")

    assert denied.status_code in (403, 404)
    assert allowed.status_code == 200
    assert allowed.data["count"] == 1
    assert allowed.data["results"][0]["item_name"] == "A Tool"


def test_admin_ledger_is_superadmin_only():
    makerspace = make_space("ledger-admin")
    manager = make_member("ledger-admin-manager", makerspace)
    superadmin = make_user(
        "ledger-admin-super",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )
    product = make_product(makerspace, name="Shared Tool")
    _request_loan(makerspace, product, "ledger-admin-holder")

    denied = authenticated_client(manager).get("/api/v1/admin/ledger")
    allowed = authenticated_client(superadmin).get("/api/v1/admin/ledger")

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.data["count"] == 1
    assert allowed.data["results"][0]["makerspace_id"] == makerspace.id


def test_ledger_reports_every_item_of_a_bundled_loan():
    """A bundled self-checkout / direct handout has one PublicToolLoan but multiple
    backing item rows + quantities; the ledger must report each item with its real
    outstanding quantity, not a single qty:1 line."""
    makerspace = make_space("ledger-bundled")
    manager = make_member("ledger-bundled-manager", makerspace)
    drill = make_product(makerspace, name="Cordless Drill")
    bits = make_product(makerspace, name="Bit Set")
    requester = make_user("ledger-bundled-holder", access_status=User.AccessStatus.ACTIVE)
    issued_at = timezone.now() - timedelta(hours=4)
    request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        status=HardwareRequest.Status.ISSUED,
        issued_at=issued_at,
    )
    HardwareRequestItem.objects.create(
        request=request, product=drill, requested_quantity=1, accepted_quantity=1, issued_quantity=1
    )
    HardwareRequestItem.objects.create(
        request=request, product=bits, requested_quantity=4, accepted_quantity=4, issued_quantity=4
    )
    PublicToolLoan.objects.create(
        makerspace=makerspace,
        request=request,
        requester=requester,
        target_type="box",
        target_id=0,
        target_label="Tool box",
        status=PublicToolLoan.Status.CHECKED_OUT,
        source=PublicToolLoan.Source.PUBLIC_SELF_CHECKOUT,
    )

    response = authenticated_client(manager).get(f"/api/v1/admin/makerspace/{makerspace.id}/ledger")

    assert response.status_code == 200
    rows = {row["item_name"]: row for row in response.data["results"]}
    assert rows["Cordless Drill"]["quantity"] == 1
    assert rows["Bit Set"]["quantity"] == 4
    assert all(row["source"] == "self_checkout" for row in response.data["results"])


def test_ledger_includes_units_and_target_label_for_individual_self_checkout():
    makerspace = make_space("ledger-individual-self")
    manager = make_member("ledger-individual-self-manager", makerspace)
    product = make_product(
        makerspace,
        name="Thermal Camera",
        tracking_mode=TrackingMode.INDIVIDUAL,
        total_quantity=1,
        available_quantity=0,
        issued_quantity=1,
    )
    asset = InventoryAsset.objects.create(
        makerspace=makerspace,
        product=product,
        asset_tag="TC-001",
        serial_number="SN-TC-001",
        status=InventoryAsset.Status.ISSUED,
    )
    loan = _self_checkout_loan(makerspace, product, "ledger-individual-holder")
    loan.asset_ids = [asset.id]
    loan.target_label = "Asset TC-001"
    loan.save(update_fields=["asset_ids", "target_label"])

    response = authenticated_client(manager).get(
        f"/api/v1/admin/makerspace/{makerspace.id}/ledger"
    )

    assert response.status_code == 200
    row = response.data["results"][0]
    assert row["source"] == "self_checkout"
    assert row["item_name"] == "Thermal Camera"
    assert row["units"] == [
        {"asset_tag": "TC-001", "serial_number": "SN-TC-001"}
    ]
    assert row["target_label"] == "Asset TC-001"


def test_ledger_quantity_tracked_loan_has_empty_units():
    makerspace = make_space("ledger-quantity-units")
    manager = make_member("ledger-quantity-units-manager", makerspace)
    product = make_product(makerspace, name="Clamp Meter")
    _self_checkout_loan(makerspace, product, "ledger-quantity-holder")

    response = authenticated_client(manager).get(
        f"/api/v1/admin/makerspace/{makerspace.id}/ledger"
    )

    assert response.status_code == 200
    assert response.data["results"][0]["item_name"] == "Clamp Meter"
    assert response.data["results"][0]["units"] == []


def test_ledger_reviewed_request_units_come_from_issued_asset_links():
    makerspace = make_space("ledger-reviewed-units")
    manager = make_member("ledger-reviewed-units-manager", makerspace)
    product = make_product(
        makerspace,
        name="Spectrum Analyzer",
        tracking_mode=TrackingMode.INDIVIDUAL,
        total_quantity=2,
        available_quantity=0,
        issued_quantity=2,
    )
    issued_asset = InventoryAsset.objects.create(
        makerspace=makerspace,
        product=product,
        asset_tag="SA-ISSUED",
        serial_number="SN-SA-1",
        status=InventoryAsset.Status.ISSUED,
    )
    returned_asset = InventoryAsset.objects.create(
        makerspace=makerspace,
        product=product,
        asset_tag="SA-RETURNED",
        serial_number="SN-SA-2",
        status=InventoryAsset.Status.AVAILABLE,
    )
    request = _request_loan(
        makerspace,
        product,
        "ledger-reviewed-holder",
        quantity=2,
        returned=1,
        status=HardwareRequest.Status.PARTIALLY_RETURNED,
    )
    item = request.items.get()
    HardwareRequestItemAsset.objects.create(
        request_item=item,
        asset=issued_asset,
        outcome=HardwareRequestItemAsset.Outcome.ISSUED,
    )
    HardwareRequestItemAsset.objects.create(
        request_item=item,
        asset=returned_asset,
        outcome=HardwareRequestItemAsset.Outcome.RETURNED,
    )

    response = authenticated_client(manager).get(
        f"/api/v1/admin/makerspace/{makerspace.id}/ledger"
    )

    assert response.status_code == 200
    row = response.data["results"][0]
    assert row["source"] == "request"
    assert row["quantity"] == 1
    assert row["target_label"] is None
    assert row["units"] == [
        {"asset_tag": "SA-ISSUED", "serial_number": "SN-SA-1"}
    ]


def test_ledger_holder_prefers_contact_email_over_checkin_username():
    makerspace = make_space("ledger-holder-email")
    manager = make_member("ledger-holder-email-manager", makerspace)
    product = make_product(makerspace, name="Soldering Iron")
    requester = make_user(
        "checkin_" + "a" * 64,
        access_status=User.AccessStatus.ACTIVE,
    )
    issued_at = timezone.now() - timedelta(hours=2)
    request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        requester_contact_email="holder@example.com",
        status=HardwareRequest.Status.ISSUED,
        issued_at=issued_at,
    )
    HardwareRequestItem.objects.create(
        request=request,
        product=product,
        requested_quantity=1,
        accepted_quantity=1,
        issued_quantity=1,
    )
    PublicToolLoan.objects.create(
        makerspace=makerspace,
        request=request,
        requester=requester,
        target_type="product",
        target_id=product.id,
        target_label=product.name,
        status=PublicToolLoan.Status.CHECKED_OUT,
    )

    response = authenticated_client(manager).get(
        f"/api/v1/admin/makerspace/{makerspace.id}/ledger"
    )

    assert response.status_code == 200
    assert response.data["results"][0]["holder"] == "holder@example.com"


def test_ledger_holder_uses_checkin_external_email_before_internal_username():
    makerspace = make_space("ledger-holder-external-email")
    manager = make_member("ledger-holder-external-email-manager", makerspace)
    product = make_product(makerspace, name="Crimp Tool")
    requester = make_user(
        "checkin_" + "b" * 64,
        access_status=User.AccessStatus.ACTIVE,
        external_checkin_user_id="external-holder@example.com",
    )
    issued_at = timezone.now() - timedelta(hours=1)
    request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username="External Holder",
        status=HardwareRequest.Status.ISSUED,
        issued_at=issued_at,
    )
    HardwareRequestItem.objects.create(
        request=request,
        product=product,
        requested_quantity=1,
        accepted_quantity=1,
        issued_quantity=1,
    )
    PublicToolLoan.objects.create(
        makerspace=makerspace,
        request=request,
        requester=requester,
        target_type="product",
        target_id=product.id,
        target_label=product.name,
        status=PublicToolLoan.Status.CHECKED_OUT,
    )

    response = authenticated_client(manager).get(
        f"/api/v1/admin/makerspace/{makerspace.id}/ledger"
    )

    assert response.status_code == 200
    assert response.data["results"][0]["holder"] == "external-holder@example.com"




def test_ledger_internal_checkin_fallback_is_member():
    makerspace = make_space("ledger-internal-fallback")
    manager = make_member("ledger-internal-fallback-manager", makerspace)
    product = make_product(makerspace, name="Loaner")
    hashed = "checkin_" + ("e" * 64)
    requester = make_user(hashed, access_status=User.AccessStatus.ACTIVE)
    _request_loan(makerspace, product, hashed, quantity=1, requester=requester)

    response = authenticated_client(manager).get(
        f"/api/v1/admin/makerspace/{makerspace.id}/ledger"
    )

    assert response.status_code == 200
    assert response.data["results"][0]["holder"] == "Member"

def test_active_loans_xlsx_export_handles_timezone_aware_datetimes():
    """active-loans rows carry tz-aware issued_at; openpyxl rejects tz-aware
    datetimes, so the XLSX export must normalize them instead of 500ing."""
    makerspace = make_space("reports-xlsx")
    manager = make_member("reports-xlsx-manager", makerspace)
    product = make_product(makerspace, name="Scope")
    _request_loan(makerspace, product, "reports-xlsx-holder", quantity=1)

    response = authenticated_client(manager).get(
        f"/api/v1/admin/makerspace/{makerspace.id}/reports/active-loans/export?format=xlsx"
    )

    assert response.status_code == 200
    assert "spreadsheetml" in response["Content-Type"]


def test_operations_reports_accept_date_range_filters():
    makerspace = make_space("reports-date-range")
    manager = make_member("reports-date-range-manager", makerspace)
    product = make_product(makerspace, name="Range Meter")
    recent = _request_loan(makerspace, product, "reports-date-recent", quantity=1)
    old = _request_loan(makerspace, product, "reports-date-old", quantity=1)
    old.issued_at = timezone.now() - timedelta(days=30)
    old.save(update_fields=["issued_at"])
    start = (timezone.now() - timedelta(days=3)).date().isoformat()
    end = timezone.now().date().isoformat()

    response = authenticated_client(manager).get(
        f"/api/v1/admin/makerspace/{makerspace.id}/analytics/taken-items?start={start}&end={end}"
    )

    assert response.status_code == 200
    assert response.data["rows"] == [["product", "issued_quantity"], ["Range Meter", 1]]
    assert recent.issued_at.date().isoformat() >= start


def test_new_makerspace_reports_return_sane_rows():
    makerspace = make_space("reports-new")
    manager = make_member("reports-new-manager", makerspace)
    alpha = make_product(makerspace, name="Alpha Kit", total_quantity=9, available_quantity=9)
    beta = make_product(makerspace, name="Beta Kit", total_quantity=5, available_quantity=5)
    older = timezone.now() - timedelta(days=5)
    newer = timezone.now() - timedelta(days=1)
    alpha.created_at = older
    beta.created_at = newer
    alpha.save(update_fields=["created_at"])
    beta.save(update_fields=["created_at"])
    alice = make_user("reports-alice", access_status=User.AccessStatus.ACTIVE)
    _request_loan(makerspace, alpha, alice.username, quantity=2, requester=alice)
    _request_loan(makerspace, alpha, alice.username, quantity=3, requester=alice)
    _request_loan(makerspace, beta, "reports-bob", quantity=1)
    client = authenticated_client(manager)

    most_lent = client.get(f"/api/v1/admin/makerspace/{makerspace.id}/analytics/most-lent")
    top_borrowers = client.get(f"/api/v1/admin/makerspace/{makerspace.id}/analytics/top-borrowers")
    recently_added = client.get(f"/api/v1/admin/makerspace/{makerspace.id}/analytics/recently-added")

    assert most_lent.status_code == 200
    assert most_lent.data["rows"][0] == ["product_name", "times_lent", "total_quantity_lent"]
    assert most_lent.data["rows"][1] == ["Alpha Kit", 2, 5]
    assert top_borrowers.status_code == 200
    assert top_borrowers.data["rows"][0] == ["holder", "requests", "items_borrowed"]
    assert top_borrowers.data["rows"][1] == ["reports-alice", 2, 5]
    assert recently_added.status_code == 200
    assert recently_added.data["rows"][0] == ["product_name", "created_at", "total_quantity"]
    assert recently_added.data["rows"][1][0] == "Beta Kit"


def test_reports_exclude_archived_products_from_active_product_surfaces():
    makerspace = make_space("reports-archived-products")
    manager = make_member("reports-archived-products-manager", makerspace)
    active = make_product(
        makerspace,
        name="Active Meter",
        total_quantity=8,
        available_quantity=4,
        issued_quantity=2,
        damaged_quantity=1,
        lost_quantity=1,
    )
    archived = make_product(
        makerspace,
        name="Archived Meter",
        total_quantity=100,
        available_quantity=76,
        issued_quantity=9,
        damaged_quantity=8,
        lost_quantity=7,
        is_archived=True,
    )
    # One asset on each product: the archived product's asset must NOT inflate the
    # summary asset total once archived inventory is excluded.
    InventoryAsset.objects.create(makerspace=makerspace, product=active, asset_tag="ACT-1")
    InventoryAsset.objects.create(makerspace=makerspace, product=archived, asset_tag="ARC-1")
    _request_loan(makerspace, active, "reports-active-holder", quantity=2)
    _request_loan(makerspace, archived, "reports-archived-holder", quantity=9)
    client = authenticated_client(manager)

    summary = client.get(f"/api/v1/admin/makerspace/{makerspace.id}/analytics/summary")
    damaged_lost = client.get(f"/api/v1/admin/makerspace/{makerspace.id}/analytics/damaged-lost")
    taken_items = client.get(f"/api/v1/admin/makerspace/{makerspace.id}/analytics/taken-items")
    most_lent = client.get(f"/api/v1/admin/makerspace/{makerspace.id}/analytics/most-lent")
    top_borrowers = client.get(f"/api/v1/admin/makerspace/{makerspace.id}/analytics/top-borrowers")

    assert summary.status_code == 200
    assert summary.data["products"] == 1
    assert summary.data["assets"] == 1
    assert summary.data["available_quantity"] == 4
    assert summary.data["issued_quantity"] == 2
    assert summary.data["damaged_quantity"] == 1
    assert summary.data["missing_quantity"] == 1
    assert damaged_lost.status_code == 200
    assert damaged_lost.data["rows"] == [
        ["product_name", "damaged_quantity", "lost_quantity"],
        ["Active Meter", 1, 1],
    ]
    assert taken_items.status_code == 200
    assert taken_items.data["rows"] == [
        ["product", "issued_quantity"],
        ["Active Meter", 2],
    ]
    assert most_lent.status_code == 200
    assert most_lent.data["rows"] == [
        ["product_name", "times_lent", "total_quantity_lent"],
        ["Active Meter", 1, 2],
    ]
    assert top_borrowers.status_code == 200
    assert top_borrowers.data["rows"] == [
        ["holder", "requests", "items_borrowed"],
        ["reports-active-holder", 1, 2],
    ]


def test_superadmin_aggregate_reports_work_and_non_superadmin_is_forbidden():
    space_a = make_space("reports-aggregate-a")
    space_b = make_space("reports-aggregate-b")
    manager = make_member("reports-aggregate-manager", space_a)
    superadmin = make_user(
        "reports-aggregate-super",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )
    product_a = make_product(space_a, name="Aggregate A")
    product_b = make_product(space_b, name="Aggregate B")
    _request_loan(space_a, product_a, "reports-aggregate-holder-a", quantity=2)
    _request_loan(space_b, product_b, "reports-aggregate-holder-b", quantity=3)

    denied_analytics = authenticated_client(manager).get("/api/v1/admin/analytics/most-lent")
    allowed_analytics = authenticated_client(superadmin).get("/api/v1/admin/analytics/most-lent")
    denied_export = authenticated_client(manager).get("/api/v1/admin/reports/most-lent/export")
    allowed_export = authenticated_client(superadmin).get("/api/v1/admin/reports/most-lent/export")

    assert denied_analytics.status_code == 403
    assert allowed_analytics.status_code == 200
    assert allowed_analytics.data["rows"][0] == [
        "makerspace_id",
        "product_name",
        "times_lent",
        "total_quantity_lent",
    ]
    assert {row[0] for row in allowed_analytics.data["rows"][1:]} == {space_a.id, space_b.id}
    assert denied_export.status_code == 403
    assert allowed_export.status_code == 200
    assert b"makerspace_id" in allowed_export.content




