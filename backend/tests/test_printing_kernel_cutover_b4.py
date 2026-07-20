"""B4 cutover gates: provenance idempotency, mismatch stop, and authority fence."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError as DrfValidationError
from rest_framework.test import APIClient

from apps.machines.models import (
    Machine, MachineConsumableAdjustment, MachineConsumablePool,
    MachineServiceRequest, MachineType, MachineUsageEntry,
    PrintingCutoverRepair, ServiceBucket, ServiceQueue,
)
from apps.machines.service_file_policies import get_policy
from apps.machines.printing_cutover import CutoverMismatch, backfill, flip_authority, kernel_is_authoritative
from apps.printing import workflow
from apps.printing.models import FilamentSpool, PrintBucket, PrintPrinter, PrintRequest
from apps.printing.public_workflow import submit_public_print_request
from apps.printing.reports import build_printing_report
from apps.printing.serializers import ManagedPrintRequestSerializer
from apps.printing.workflow_errors import PrintStartValidationError
from tests.return_helpers import make_space, make_user
from tests.test_printing import authenticated_client, make_print_manager


pytestmark = pytest.mark.django_db


def _legacy_space(slug):
    space, user = make_space(slug), make_user(f"{slug}-requester")
    bucket = PrintBucket.objects.create(makerspace=space, name="Print queue")
    printer = PrintPrinter.objects.create(makerspace=space, name="MK4", model="Prusa MK4")
    spool = FilamentSpool.objects.create(
        makerspace=space, printer=printer, material="PLA", color="Blue",
        initial_weight_grams=Decimal("100"), remaining_weight_grams=Decimal("100"),
    )
    request = PrintRequest.objects.create(
        bucket=bucket, requester=user, title="Bracket", material="PLA", color="Blue", quantity=1,
        requested_filament_spool=spool,
    )
    return space, user, bucket, printer, spool, request


def test_backfill_is_idempotent_and_flip_makes_legacy_read_only():
    space, user, _, _, _, legacy = _legacy_space("b4-idempotent")
    first, second = backfill(space), backfill(space)
    assert first.pk == second.pk
    kernel = MachineServiceRequest.objects.get(legacy_print_request_id=legacy.pk)
    assert kernel.public_token == legacy.public_token
    assert MachineServiceRequest.objects.filter(makerspace=space).count() == 1

    flip_authority(space)
    assert kernel_is_authoritative(space)
    with pytest.raises(ValidationError, match="read-only"):
        PrintRequest.objects.create(bucket=legacy.bucket, requester=user, title="Forbidden")


def test_reconciliation_stops_and_records_a_forward_repair():
    space, _, _, _, spool, _ = _legacy_space("b4-mismatch")
    spool.remaining_weight_grams = Decimal("90")
    spool.save(update_fields=["remaining_weight_grams"])
    with pytest.raises(CutoverMismatch, match="Ledger balance"):
        backfill(space)
    assert PrintingCutoverRepair.objects.filter(
        makerspace=space, kind="mismatch", legacy_model="machines.printing_cutover"
    ).exists()


def test_kernel_submit_never_creates_a_legacy_default_queue():
    space, user, bucket, _, _, _ = _legacy_space("b4-kernel-public-queue")
    backfill(space)
    flip_authority(space)

    # The old fallback would create a new PrintBucket called "Public Requests".
    # A flipped tenant has no such kernel queue, so it must fail closed instead.
    with pytest.raises(DrfValidationError, match="Select an active reconciled"):
        submit_public_print_request(space, {"title": "No implicit queue"}, user)
    assert PrintBucket.objects.filter(makerspace=space, name="Public Requests").count() == 0
    assert bucket.name == "Print queue"


def test_kernel_public_default_ignores_non_reconciled_queue():
    space, user, _, _, _, _ = _legacy_space("b4-nonreconciled-default")
    backfill(space)
    flip_authority(space)
    printer_type = MachineType.objects.get(makerspace__isnull=True, slug="3d_printer")
    ServiceQueue.objects.create(
        makerspace=space, machine_type=printer_type, name="Public Requests",
    )

    with pytest.raises(DrfValidationError, match="Select an active reconciled"):
        submit_public_print_request(space, {"title": "No implicit queue"}, user)


def test_kernel_public_submit_preserves_no_preference_and_grams():
    space, user, bucket, _, _, _ = _legacy_space("b4-public-preference")
    bucket.name = "Public Requests"
    bucket.save(update_fields=["name"])
    space.enabled_modules = ["printing", "machine_service"]
    space.save(update_fields=["enabled_modules"])
    backfill(space)
    flip_authority(space)

    request = submit_public_print_request(
        space,
        {"title": "Any filament", "estimated_filament_grams": Decimal("12.50")},
        user,
    )

    assert request.legacy_print_request_id is None
    assert request.capability_payload["no_filament_preference"] is True
    assert request.capability_payload["estimated_grams"] == "12.50"
    assert request.capability_payload["requested_material"] == "PLA"
    assert request.capability_payload["requested_color"] == "Black"


def test_print_manager_lists_and_accepts_kernel_created_print_request():
    space, user, bucket, _, _, _ = _legacy_space("b4-print-manager-kernel")
    bucket.name = "Public Requests"
    bucket.save(update_fields=["name"])
    space.enabled_modules = ["printing", "machine_service"]
    space.save(update_fields=["enabled_modules"])
    backfill(space)
    flip_authority(space)
    kernel = submit_public_print_request(space, {"title": "Kernel only"}, user)
    manager = make_print_manager("b4-print-manager", space)
    client = authenticated_client(manager)

    listed = client.get(reverse("printing:managed-request-list"))
    assert listed.status_code == 200
    assert -kernel.pk in [row["id"] for row in listed.data["results"]]

    accepted = client.post(
        reverse("printing:managed-request-accept", kwargs={"pk": -kernel.pk}),
        {"price": "0"}, format="json",
    )
    assert accepted.status_code == 200
    kernel.refresh_from_db()
    assert kernel.status == MachineServiceRequest.Status.ACCEPTED


def test_historical_ledger_inserts_preserve_timestamp_without_field_mutation():
    space, _, _, _, _, _ = _legacy_space("b4-historical-timestamps")
    backfill(space)
    machine = Machine.objects.get(makerspace=space)
    pool = MachineConsumablePool.objects.get(makerspace=space)
    historical = timezone.now() - timedelta(days=2)

    usage = MachineUsageEntry(machine=machine, hours=Decimal("1"), created_at=historical)
    usage.save(preserve_created_at=True)
    adjustment = MachineConsumableAdjustment(
        makerspace=space, consumable_pool=pool, kind="manual",
        quantity_delta=Decimal("1"), created_at=historical,
    )
    adjustment.save(preserve_created_at=True)

    assert usage.created_at == historical
    assert adjustment.created_at == historical
    assert MachineUsageEntry._meta.get_field("created_at").auto_now_add is True
    assert MachineConsumableAdjustment._meta.get_field("created_at").auto_now_add is True


def test_kernel_start_rejects_unknown_legacy_printer_or_spool_ids_as_typed_errors():
    space, user, _, _, _, legacy = _legacy_space("b4-kernel-invalid-start")
    backfill(space)
    flip_authority(space)
    with pytest.raises(PrintStartValidationError, match="Invalid printer"):
        workflow.start(
            legacy, user, printer_id=999999, filament_spool_id=999999,
            estimated_minutes=10, estimated_filament_grams=Decimal("1"),
        )


def test_public_status_reads_the_authoritative_kernel_request():
    space, user, _, printer, spool, legacy = _legacy_space("b4-kernel-public-status")
    space.enabled_modules = ["printing", "machine_service"]
    space.save(update_fields=["enabled_modules"])
    backfill(space)
    flip_authority(space)
    workflow.accept(legacy, user)
    workflow.start(
        legacy, user, printer_id=printer.pk, filament_spool_id=spool.pk,
        estimated_minutes=10, estimated_filament_grams=Decimal("1"),
    )

    response = APIClient().get(reverse(
        "printing:public-request-status", kwargs={"public_token": legacy.public_token},
    ))
    assert response.status_code == 200
    assert response.data["status"] == "printing"


def test_kernel_action_result_keeps_the_managed_legacy_response_shape():
    space, user, _, _, _, legacy = _legacy_space("b4-kernel-response-adapter")
    space.enabled_modules = ["printing", "machine_service"]
    space.save(update_fields=["enabled_modules"])
    backfill(space)
    flip_authority(space)

    response = ManagedPrintRequestSerializer(workflow.accept(legacy, user)).data
    assert response["id"] == -MachineServiceRequest.objects.get(legacy_print_request_id=legacy.pk).pk
    assert response["status"] == PrintRequest.Status.ACCEPTED
    assert response["price"] == "0.00"


def test_kernel_start_projects_its_authoritative_printer_and_spool():
    space, user, _, printer, spool, legacy = _legacy_space("b4-kernel-start-projection")
    space.enabled_modules = ["printing", "machine_service"]
    space.save(update_fields=["enabled_modules"])
    backfill(space)
    flip_authority(space)
    workflow.accept(legacy, user)

    response = ManagedPrintRequestSerializer(workflow.start(
        legacy, user, printer_id=printer.pk, filament_spool_id=spool.pk,
        estimated_minutes=10, estimated_filament_grams=Decimal("1"),
    )).data
    assert response["printer"]["id"] == printer.pk
    assert response["filament_spool"]["id"] == spool.pk


def test_kernel_reprint_returns_the_new_kernel_request_identifier():
    space, user, _, _, _, legacy = _legacy_space("b4-kernel-reprint-id")
    legacy.status = PrintRequest.Status.FAILED
    legacy.reason = "Bad adhesion"
    legacy.save(update_fields=["status", "reason"])
    space.enabled_modules = ["printing", "machine_service"]
    space.save(update_fields=["enabled_modules"])
    backfill(space)
    flip_authority(space)

    response = ManagedPrintRequestSerializer(workflow.reprint(legacy, user)).data
    assert response["id"] != legacy.pk
    assert response["status"] == PrintRequest.Status.ACCEPTED


def test_printer_policy_retains_the_public_print_upload_contract():
    policy = get_policy("printer", 1)
    assert policy.max_bytes == settings.PRINT_UPLOAD_MAX_BYTES
    assert "application/octet-stream" in policy.allowed_mimes
    assert {"stl", "3mf"}.issubset(policy.allowed_extensions)


def test_public_print_status_never_exposes_a_non_print_kernel_request():
    space, user, _, _, _, _ = _legacy_space("b4-non-print-status")
    backfill(space)
    flip_authority(space)
    type_ = MachineType.objects.create(makerspace=space, name="Laser", slug="laser")
    machine = Machine.objects.create(makerspace=space, machine_type=type_, name="Laser cutter")
    bucket = ServiceBucket.objects.create(machine=machine, name="Service")
    other = MachineServiceRequest.objects.create(
        bucket=bucket, makerspace=space, requester=user, title="Private laser request",
    )

    response = APIClient().get(reverse(
        "printing:public-request-status", kwargs={"public_token": other.public_token},
    ))
    assert response.status_code == 404


def test_flip_requires_machine_service_and_it_cannot_be_disabled_afterward():
    space, _, _, _, _, _ = _legacy_space("b4-module-boundary")
    space.enabled_modules = [name for name in space.enabled_modules if name != "machine_service"]
    space.save(update_fields=["enabled_modules"])
    backfill(space)

    with pytest.raises(ValidationError, match="Machine service must remain enabled"):
        flip_authority(space)
    assert not kernel_is_authoritative(space)

    space.enabled_modules.append("machine_service")
    space.save(update_fields=["enabled_modules"])
    flip_authority(space)
    space.enabled_modules.remove("machine_service")
    with pytest.raises(ValidationError, match="cannot be disabled"):
        space.save(update_fields=["enabled_modules"])


def test_personal_request_endpoints_project_authoritative_kernel_rows():
    space, user, bucket, _, _, _ = _legacy_space("b4-personal-kernel-rows")
    bucket.name = "Public Requests"
    bucket.save(update_fields=["name"])
    space.enabled_modules = ["printing", "machine_service"]
    space.save(update_fields=["enabled_modules"])
    backfill(space)
    flip_authority(space)
    kernel = submit_public_print_request(space, {"title": "Kernel-only personal row"}, user)
    client = authenticated_client(user)

    listed = client.get(reverse("printing:request-list"))
    assert listed.status_code == 200
    row = next(row for row in listed.data["results"] if row["id"] == -kernel.pk)
    assert row["status"] == PrintRequest.Status.PENDING

    from apps.machines.service_workflow import accept as kernel_accept
    kernel_accept(kernel, user)
    detail = client.get(reverse("printing:request-detail", kwargs={"pk": -kernel.pk}))
    assert detail.status_code == 200
    assert detail.data["id"] == -kernel.pk
    assert detail.data["status"] == PrintRequest.Status.ACCEPTED


def test_kernel_public_submit_keeps_monthly_print_quota(monkeypatch):
    space, user, bucket, _, _, _ = _legacy_space("b4-kernel-print-quota")
    bucket.name = "Public Requests"
    bucket.save(update_fields=["name"])
    space.enabled_modules = ["printing", "machine_service"]
    space.resource_limit_overrides = {"print": 0}
    space.save(update_fields=["enabled_modules", "resource_limit_overrides"])
    backfill(space)
    flip_authority(space)
    monkeypatch.setattr("apps.makerspaces.limits.is_self_host", lambda: False)

    with pytest.raises(DrfValidationError, match="free monthly print requests"):
        submit_public_print_request(space, {"title": "Over quota"}, user)


def test_printing_report_reads_kernel_rows_after_cutover():
    space, user, _, printer, spool, legacy = _legacy_space("b4-kernel-report")
    space.enabled_modules = ["printing", "machine_service"]
    space.save(update_fields=["enabled_modules"])
    backfill(space)
    flip_authority(space)
    workflow.accept(legacy, user)
    workflow.start(
        legacy, user, printer_id=printer.pk, filament_spool_id=spool.pk,
        estimated_minutes=12, estimated_filament_grams=Decimal("2"),
    )
    workflow.complete(legacy, user, actual_filament_grams=Decimal("2"))

    report = build_printing_report(space.pk)
    assert report["totals"]["completed"] == 1
    assert report["printer_hours"][0]["printer_id"] == printer.pk
    assert report["printer_hours"][0]["completed_requests"] == 1


def test_personal_post_routes_a_flipped_tenant_to_kernel_with_compatibility_data():
    space, user, bucket, _, _, _ = _legacy_space("b4-personal-post")
    bucket.name = "Public Requests"
    bucket.save(update_fields=["name"])
    space.enabled_modules = ["printing", "machine_service"]
    space.save(update_fields=["enabled_modules"])
    backfill(space)
    flip_authority(space)

    response = authenticated_client(user).post(reverse("printing:request-list"), {
        "bucket": bucket.pk,
        "title": "Personal kernel request",
        "description": "A direct requester submission",
        "material": "PLA",
        "color": "Blue",
        "quantity": 2,
        "preferred_settings": '{"layer_height": "0.2"}',
    }, format="json")

    assert response.status_code == 201
    assert response.data["id"] < 0
    kernel = MachineServiceRequest.objects.get(pk=-response.data["id"])
    assert kernel.member_id == user.pk
    assert kernel.capability_payload["quantity"] == 2
    assert kernel.capability_payload["preferred_settings"] == {"layer_height": "0.2"}
    assert response.data["preferred_settings"] == '{"layer_height": "0.2"}'


def test_kernel_ids_are_negative_for_managed_detail_and_actions():
    space, user, bucket, _, _, _ = _legacy_space("b4-managed-negative-ids")
    bucket.name = "Public Requests"
    bucket.save(update_fields=["name"])
    space.enabled_modules = ["printing", "machine_service"]
    space.save(update_fields=["enabled_modules"])
    backfill(space)
    flip_authority(space)
    kernel = submit_public_print_request(space, {"title": "Kernel namespace"}, user)
    manager = make_print_manager("b4-negative-id-manager", space)
    client = authenticated_client(manager)

    assert client.get(reverse("printing:managed-request-detail", kwargs={"pk": kernel.pk})).status_code == 404
    detail = client.get(reverse("printing:managed-request-detail", kwargs={"pk": -kernel.pk}))
    assert detail.status_code == 200
    assert detail.data["id"] == -kernel.pk
    accepted = client.post(
        reverse("printing:managed-request-accept", kwargs={"pk": -kernel.pk}),
        {"price": "0", "estimated_filament_grams": "3.50"}, format="json",
    )
    assert accepted.status_code == 200
    assert accepted.data["id"] == -kernel.pk


def test_kernel_accept_persists_grams_and_start_uses_that_plan_by_default():
    space, user, _, printer, spool, legacy = _legacy_space("b4-accept-grams")
    space.enabled_modules = ["printing", "machine_service"]
    space.save(update_fields=["enabled_modules"])
    backfill(space)
    flip_authority(space)

    workflow.accept(legacy, user, estimated_filament_grams=Decimal("4.25"))
    kernel = MachineServiceRequest.objects.get(legacy_print_request_id=legacy.pk)
    assert kernel.planned_grams == Decimal("4.25")
    assert kernel.capability_payload["estimated_grams"] == "4.25"
    workflow.start(
        legacy, user, printer_id=printer.pk, filament_spool_id=spool.pk,
        estimated_minutes=10,
    )
    kernel.refresh_from_db()
    assert kernel.run_planned_grams == Decimal("4.25")


def test_kernel_public_submission_retains_schema_valid_preferred_settings():
    space, user, bucket, _, _, _ = _legacy_space("b4-public-settings")
    bucket.name = "Public Requests"
    bucket.save(update_fields=["name"])
    space.enabled_modules = ["printing", "machine_service"]
    space.save(update_fields=["enabled_modules"])
    backfill(space)
    flip_authority(space)

    request = submit_public_print_request(
        space, {"title": "Fine detail", "preferred_settings": '{"infill": 15}'}, user,
    )
    assert request.capability_payload["preferred_settings"] == {"infill": 15}
    assert ManagedPrintRequestSerializer(workflow.legacy_compatible_response(request)).data["preferred_settings"] == '{"infill": 15}'


def test_kernel_public_status_returns_real_approved_and_pending_queue_counts():
    space, user, bucket, _, _, _ = _legacy_space("b4-public-queue-counts")
    bucket.name = "Public Requests"
    bucket.save(update_fields=["name"])
    space.enabled_modules = ["printing", "machine_service"]
    space.save(update_fields=["enabled_modules"])
    backfill(space)
    flip_authority(space)
    approved = submit_public_print_request(space, {"title": "Approved first"}, user)
    pending = submit_public_print_request(space, {"title": "Pending second"}, user)
    from apps.machines.service_workflow import accept as kernel_accept
    kernel_accept(approved, user)

    response = APIClient().get(reverse(
        "printing:public-request-status", kwargs={"public_token": pending.public_token},
    ))
    assert response.status_code == 200
    # The reconciled historical request is pending ahead, plus this accepted request.
    assert response.data["queue_approved_ahead"] == 1
    assert response.data["queue_awaiting_review_ahead"] == 1
    assert response.data["queue_position"] == 3
