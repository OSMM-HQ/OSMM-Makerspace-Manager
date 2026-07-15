from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from rest_framework.serializers import ValidationError

from apps.admin_api.bulk_import import apply_import
from apps.apiclients.models import ApiClient
from apps.evidence.models import EvidencePhoto
from apps.integrations.dispatch import dispatch_email
from apps.integrations.models import DailyEmailCounter, EmailLog
from apps.inventory.models import InventoryProduct
from apps.machines.models import Machine, MachineType
from apps.makerspaces import limits
from apps.makerspaces.models import Makerspace, MakerspaceMembership
from apps.printing.models import PrintBucket, PrintRequest
from tests.return_helpers import authenticated_client, make_member, make_space, make_user

pytestmark = pytest.mark.django_db
ROW_LIMIT_CASES = ("products", "machines", "staff", "api_clients", "print")


def _active_count(makerspace, case):
    if case == "products":
        return InventoryProduct.objects.filter(
            makerspace=makerspace, is_archived=False
        ).count()
    if case == "machines":
        return Machine.objects.filter(makerspace=makerspace, is_active=True).count()
    if case == "staff":
        return MakerspaceMembership.objects.filter(
            makerspace=makerspace,
            user__is_active=True,
            user__access_status="active",
        ).count()
    if case == "api_clients":
        return ApiClient.objects.filter(makerspace=makerspace, is_active=True).count()
    return PrintRequest.objects.filter(bucket__makerspace=makerspace).count()


def _attempt_second_row(case, mode):
    makerspace = make_space(f"limits-{case.replace('_', '-')}-{mode}")
    makerspace.resource_limit_overrides = {case: 1}
    makerspace.save(update_fields=["resource_limit_overrides"])

    if case == "print":
        bucket = PrintBucket.objects.create(makerspace=makerspace, name="PLA")
        requester = make_user(f"limits-print-requester-{mode}", access_status="active")
        PrintRequest.objects.create(
            bucket=bucket, requester=requester, title="Existing print"
        )
        response = authenticated_client(requester).post(
            reverse("printing:request-list"),
            {"bucket": bucket.id, "title": "Second print", "quantity": 1},
            format="json",
            HTTP_HOST="testserver",
        )
        return makerspace, response

    manager = make_member(f"limits-{case}-manager-{mode}", makerspace)
    client = authenticated_client(manager)
    if case == "products":
        InventoryProduct.objects.create(
            makerspace=makerspace, name="Existing product", is_archived=False
        )
        response = client.post(
            reverse("admin-inventory", kwargs={"makerspace_id": makerspace.id}),
            {"name": "Second product", "total_quantity": 1, "available_quantity": 1},
            format="json",
            HTTP_HOST="testserver",
        )
    elif case == "machines":
        machine_type = MachineType.objects.create(
            makerspace=makerspace, slug="quota-tool", name="Quota Tool"
        )
        Machine.objects.create(
            makerspace=makerspace,
            machine_type=machine_type,
            name="Existing machine",
            created_by=manager,
        )
        response = client.post(
            reverse("admin-machines", kwargs={"makerspace_id": makerspace.id}),
            {"machine_type_id": machine_type.id, "name": "Second machine"},
            format="json",
            HTTP_HOST="testserver",
        )
    elif case == "staff":
        response = client.post(
            "/api/v1/admin/users/inventory-managers",
            {
                "username": f"limits-second-staff-{mode}",
                "email": f"limits-second-staff-{mode}@example.com",
                "makerspace_id": makerspace.id,
                "role": "inventory_manager",
            },
            format="json",
            HTTP_HOST="testserver",
        )
    else:
        ApiClient.issue(
            label="Existing client",
            makerspace=makerspace,
            allowed_origins=["https://existing.example"],
        )
        response = client.post(
            f"/api/v1/admin/makerspace/{makerspace.id}/api-clients",
            {"label": "Second client", "allowed_origins": ["https://second.example"]},
            format="json",
            HTTP_HOST="testserver",
        )
    return makerspace, response


@override_settings(
    PLATFORM_DOMAIN_SUFFIX=".osmm.me",
    INFRA_HOSTS={"testserver"},
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
@pytest.mark.parametrize("case", ROW_LIMIT_CASES)
def test_managed_row_create_paths_reject_the_second_active_row(case):
    makerspace, response = _attempt_second_row(case, "managed")

    assert response.status_code == 400
    assert "limit" in response.data
    assert "limit" in str(response.data["limit"]).lower()
    assert _active_count(makerspace, case) == 1


@override_settings(
    PLATFORM_DOMAIN_SUFFIX="",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
@pytest.mark.parametrize("case", ROW_LIMIT_CASES)
def test_self_host_row_create_paths_ignore_managed_caps(case):
    makerspace, response = _attempt_second_row(case, "self-host")

    assert response.status_code == 201
    assert _active_count(makerspace, case) == 2


def _import_rows(count):
    return [
        {
            "name": f"Imported product {index}",
            "total_quantity": "1",
            "available_quantity": "1",
        }
        for index in range(count)
    ]


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me")
def test_managed_bulk_import_checks_all_new_names_before_writing():
    makerspace = make_space("limits-bulk-import")
    actor = make_member("limits-bulk-import-manager", makerspace)
    makerspace.resource_limit_overrides = {"products": 2}
    makerspace.save(update_fields=["resource_limit_overrides"])

    with pytest.raises(ValidationError) as exc_info:
        apply_import(actor, makerspace, _import_rows(3), None)

    assert "limit" in exc_info.value.detail
    assert InventoryProduct.objects.filter(makerspace=makerspace).count() == 0
    result = apply_import(actor, makerspace, _import_rows(2), None)
    assert result["applied"] is True
    assert result["created"] == 2
    assert InventoryProduct.objects.filter(makerspace=makerspace).count() == 2


def _dispatch(makerspace=None, *, connection="makerspace", subject="Quota email"):
    return dispatch_email(
        to_email="recipient@example.com",
        subject=subject,
        text_body="Fair-use enforcement test.",
        makerspace=makerspace,
        connection=connection,
        sync=True,
    )


@override_settings(
    PLATFORM_DOMAIN_SUFFIX=".osmm.me",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_managed_makerspace_email_daily_cap_blocks_delivery(mailoutbox):
    makerspace = make_space("limits-email-managed")
    makerspace.resource_limit_overrides = {"email": 1}
    makerspace.save(update_fields=["resource_limit_overrides"])

    first = _dispatch(makerspace, subject="First")
    second = _dispatch(makerspace, subject="Second")

    assert first.status == EmailLog.Status.SENT
    assert second.status == EmailLog.Status.FAILED
    assert "daily" in second.error.lower() and "limit" in second.error.lower()
    assert len(mailoutbox) == 1
    counter = DailyEmailCounter.objects.get(makerspace=makerspace)
    assert counter.count == 1
    assert DailyEmailCounter.objects.filter(makerspace=makerspace).count() == 1


@override_settings(
    PLATFORM_DOMAIN_SUFFIX="",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_self_host_makerspace_email_is_never_capped(mailoutbox):
    makerspace = make_space("limits-email-self-host")
    makerspace.resource_limit_overrides = {"email": 1}
    makerspace.save(update_fields=["resource_limit_overrides"])

    logs = [_dispatch(makerspace, subject=f"Self-host {index}") for index in range(2)]

    assert [log.status for log in logs] == [EmailLog.Status.SENT] * 2
    assert len(mailoutbox) == 2
    assert not DailyEmailCounter.objects.filter(makerspace=makerspace).exists()


@override_settings(
    PLATFORM_DOMAIN_SUFFIX=".osmm.me",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_managed_platform_email_is_never_capped(mailoutbox):
    logs = [
        _dispatch(None, connection="platform", subject=f"Platform {index}")
        for index in range(2)
    ]

    assert [log.status for log in logs] == [EmailLog.Status.SENT] * 2
    assert len(mailoutbox) == 2
    assert DailyEmailCounter.objects.count() == 0


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me")
def test_managed_storage_add_free_boundary_and_clamp_without_outer_atomic():
    makerspace = make_space("limits-storage-managed")
    makerspace.resource_limit_overrides = {"storage": 100}
    makerspace.save(update_fields=["resource_limit_overrides"])

    limits.add_storage(makerspace, 60)
    makerspace.refresh_from_db()
    assert makerspace.storage_bytes_used == 60

    with pytest.raises(ValidationError):
        limits.add_storage(makerspace, 60)
    makerspace.refresh_from_db()
    assert makerspace.storage_bytes_used == 60

    limits.free_storage(makerspace, 40)
    makerspace.refresh_from_db()
    assert makerspace.storage_bytes_used == 20
    limits.free_storage(makerspace, 999)
    makerspace.refresh_from_db()
    assert makerspace.storage_bytes_used == 0


@override_settings(PLATFORM_DOMAIN_SUFFIX="")
def test_self_host_storage_accounting_is_a_noop():
    makerspace = make_space("limits-storage-self-host")
    makerspace.resource_limit_overrides = {"storage": 1}
    makerspace.storage_bytes_used = 7
    makerspace.save(update_fields=["resource_limit_overrides", "storage_bytes_used"])

    limits.add_storage(makerspace, 999)
    limits.free_storage(makerspace, 999)

    makerspace.refresh_from_db()
    assert makerspace.storage_bytes_used == 7


def test_recompute_storage_sums_authoritative_evidence_sizes():
    makerspace = make_space("limits-storage-recompute")
    uploader = make_user("limits-storage-uploader", access_status="active")
    for index, size in enumerate((40, 60)):
        EvidencePhoto.objects.create(
            makerspace=makerspace,
            evidence_type=EvidencePhoto.EvidenceType.ISSUE,
            object_key=f"evidence/{makerspace.id}/quota-{index}.jpg",
            content_type="image/jpeg",
            size_bytes=size,
            uploaded_by=uploader,
        )
    Makerspace.objects.filter(pk=makerspace.pk).update(storage_bytes_used=999)

    call_command("recompute_storage", makerspace.slug, stdout=StringIO())

    makerspace.refresh_from_db()
    assert makerspace.storage_bytes_used == 100
