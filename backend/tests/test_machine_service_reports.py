import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.machines.models import (
    Machine, MachineConsumable, MachineServiceRequest, MachineType,
    ServiceBucket, ServiceRequestConsumption,
)
from apps.machines.service_reports import build_machine_service_report, report_sections
from apps.machines.service_reports_serializers import MachineServiceReportSerializer
from tests.return_helpers import make_product, make_space, make_user


pytestmark = pytest.mark.django_db


def machine(space, name="Service machine"):
    kind = MachineType.objects.create(makerspace=space, slug=f"service-report-{space.id}-{name}", name="Service type")
    return Machine.objects.create(makerspace=space, machine_type=kind, name=name)


def service_request(space, target, *, status, created_at, completed_at=None, failed_at=None, estimated=0, actual=0, percent=0, requester=None):
    bucket, _ = ServiceBucket.objects.get_or_create(machine=target, name="Service")
    row = MachineServiceRequest.objects.create(
        bucket=bucket, requester=requester or make_user(f"report-requester-{space.id}-{MachineServiceRequest.objects.count()}"),
        title="Private repair title", status=status, estimated_minutes=estimated, actual_minutes=actual,
        fail_percent_complete=percent, reason="Private manager reason", requester_name="Private requester",
        contact_email="private@example.test", contact_phone="555-0100",
    )
    MachineServiceRequest.objects.filter(pk=row.pk).update(created_at=created_at, completed_at=completed_at, failed_at=failed_at)
    row.refresh_from_db()
    return row


def consume(row, *, measurement, quantity, outcome, label="Private consumable"):
    product = make_product(row.makerspace, name=f"Product {measurement} {row.pk}") if measurement == "count" else None
    consumable = MachineConsumable.objects.create(machine=row.assigned_machine, product=product, measurement=measurement, label=label)
    return ServiceRequestConsumption.objects.create(
        service_request=row, machine_consumable=consumable, measurement=measurement, product=product,
        label=label, quantity=quantity, outcome=outcome,
    )


def rows(result, kind):
    return [row for row in result.records if row["row_kind"] == kind]


def test_scope_date_boundaries_and_completed_failed_hours():
    space, other = make_space("service-report-scope"), make_space("service-report-other")
    target = machine(space)
    other_target = machine(other)
    start = timezone.now().replace(microsecond=0)
    service_request(space, target, status="completed", created_at=start, completed_at=start, actual=90)
    failed = service_request(space, target, status="failed", created_at=start - timedelta(days=1), failed_at=start + timedelta(hours=1), estimated=120, percent=25)
    service_request(space, target, status="pending", created_at=start + timedelta(days=1))
    service_request(other, other_target, status="completed", created_at=start, completed_at=start, actual=60)

    report = build_machine_service_report(space.id, date_range=(start, start + timedelta(days=1)))
    status = rows(report, "status")[0]
    machine_row = rows(report, "machine")[0]
    assert status["submitted"] == 1
    assert machine_row["completed_hours"] == 1.5
    assert machine_row["failed_partial_hours"] == 0.5
    assert machine_row["total_recorded_service_hours"] == 2.0
    assert machine_row["failure_rate"] == 50.0
    assert all(row.get("machine_id") != other_target.id for row in report.records)
    assert failed.assigned_machine_id == target.id


def test_consumption_measurements_are_separate_and_report_has_no_pii_or_reasons():
    space, target = make_space("service-report-consumption"), None
    target = machine(space)
    at = timezone.now().replace(microsecond=0)
    completed = service_request(space, target, status="completed", created_at=at, completed_at=at, actual=30)
    failed = service_request(space, target, status="failed", created_at=at, failed_at=at, estimated=60, percent=50)
    consume(completed, measurement="count", quantity=Decimal("2"), outcome="completed", label="Widget")
    consume(failed, measurement="grams", quantity=Decimal("3.25"), outcome="failed", label="Widget")

    report = build_machine_service_report(space.id, date_range=(at, at + timedelta(days=1)))
    consumption = rows(report, "consumption")
    assert {(row["measurement"], row["total_used"]) for row in consumption} == {
        ("count", Decimal("2.00")), ("grams", Decimal("3.25")),
    }
    failure = rows(report, "failure")[0]
    assert failure["failed_count_amount"] == Decimal("0.00")
    assert failure["failed_grams_amount"] == Decimal("3.25")
    serialized = json.dumps(MachineServiceReportSerializer(report_sections(report)).data)
    for private in ("Private requester", "private@example.test", "555-0100", "Private manager reason", "Private repair title"):
        assert private not in serialized


def test_aggregate_is_grouped_and_excludes_ineligible_makerspaces():
    eligible = make_space("service-report-eligible")
    target = machine(eligible)
    at = timezone.now()
    service_request(eligible, target, status="pending", created_at=at)
    for name, field, value in (("disabled", "enabled_modules", ["machines", "machine_service"]), ("hidden", "superadmin_access_enabled", False), ("archived", "archived_at", at)):
        space = make_space(f"service-report-{name}")
        setattr(space, field, value)
        space.save(update_fields=[field])
        service_request(space, machine(space), status="pending", created_at=at)

    result = build_machine_service_report(None)
    ids = {row["makerspace_id"] for row in result.records}
    assert ids == {eligible.id}
    assert all("makerspace_id" in row for row in result.records)
    assert [row["makerspace_id"] for row in result.records] == sorted(row["makerspace_id"] for row in result.records)


def test_report_queries_are_constant_as_requests_grow(django_assert_num_queries):
    space, target = make_space("service-report-queries"), None
    target = machine(space)
    at = timezone.now()
    for index in range(8):
        service_request(space, target, status="completed", created_at=at, completed_at=at, actual=index + 1)
    with django_assert_num_queries(3):
        result = build_machine_service_report(space.id)
        assert rows(result, "machine")[0]["request_count"] == 8
