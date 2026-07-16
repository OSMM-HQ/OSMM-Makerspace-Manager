import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.machines.models import Machine, MachineOperator
from apps.makerspaces.models import MakerspaceMembership
from apps.maintenance.models import MaintenanceLog, MaintenanceSchedule
from tests.maintenance.helpers import make_machine_setup
from tests.return_helpers import authenticated_client, make_member


pytestmark = pytest.mark.django_db


def schedule_url(makerspace, machine):
    return reverse(
        "admin-maintenance-schedule-list-create",
        kwargs={"makerspace_id": makerspace.id, "machine_id": machine.id},
    )


def log_url(makerspace, machine):
    return reverse(
        "admin-maintenance-log-list-create",
        kwargs={"makerspace_id": makerspace.id, "machine_id": machine.id},
    )


def test_machine_manager_can_create_and_list_schedules_and_logs():
    makerspace, manager, machine, _ = make_machine_setup("maintenance-api-manager")
    client = authenticated_client(manager)
    created_schedule = client.post(
        schedule_url(makerspace, machine),
        {
            "description": "Monthly calibration",
            "interval_days": 30,
            "next_due": timezone.localdate().isoformat(),
        },
        format="json",
    )
    created_log = client.post(
        log_url(makerspace, machine),
        {"summary": "Cleaned and calibrated", "cost": "2.50"},
        format="json",
    )
    listed = client.get(log_url(makerspace, machine))

    assert created_schedule.status_code == 201
    assert created_log.status_code == 201
    assert listed.status_code == 200
    assert listed.data["results"][0]["summary"] == "Cleaned and calibrated"
    assert "performed_by_id" in listed.data["results"][0]
    assert client.get(
        reverse(
            "admin-maintenance-schedule-detail",
            kwargs={"pk": created_schedule.data["id"]},
        )
    ).status_code == 405


def test_operate_can_log_but_schedule_mutation_is_403():
    makerspace, _, machine, operator = make_machine_setup(
        "maintenance-api-operate",
        operator_level=MachineOperator.AccessLevel.OPERATE,
    )
    client = authenticated_client(operator)
    logged = client.post(
        log_url(makerspace, machine),
        {"summary": "Operator maintenance"},
        format="json",
    )
    forbidden = client.post(
        schedule_url(makerspace, machine),
        {
            "description": "Not allowed",
            "interval_days": 7,
            "next_due": timezone.localdate().isoformat(),
        },
        format="json",
    )
    assert logged.status_code == 201
    assert forbidden.status_code == 403


def test_cross_tenant_and_mismatched_schedule_are_404_before_403():
    makerspace, _, machine, operator = make_machine_setup(
        "maintenance-api-scope",
        operator_level=MachineOperator.AccessLevel.OPERATE,
    )
    other, other_manager, other_machine, _ = make_machine_setup(
        "maintenance-api-other",
    )
    schedule = MaintenanceSchedule.objects.create(
        machine=other_machine,
        description="Foreign",
        interval_days=1,
        next_due=timezone.localdate(),
        created_by=other_manager,
    )
    client = authenticated_client(operator)

    cross_tenant = client.get(log_url(other, other_machine))
    mismatched = client.post(
        log_url(makerspace, machine),
        {"summary": "No", "schedule_id": schedule.id},
        format="json",
    )
    assert cross_tenant.status_code == 404
    assert mismatched.status_code == 404


def test_module_gate_and_retired_conflict_are_typed():
    makerspace, manager, machine, _ = make_machine_setup("maintenance-api-errors")
    client = authenticated_client(manager)
    machine.is_active = False
    machine.save(update_fields=["is_active"])
    retired = client.post(
        log_url(makerspace, machine),
        {"summary": "No"},
        format="json",
    )
    assert retired.status_code == 409
    assert retired.data["code"] == "machine_retired"

    makerspace.enabled_modules = [
        name for name in makerspace.enabled_modules if name != "maintenance"
    ]
    makerspace.save(update_fields=["enabled_modules"])
    disabled = client.get(log_url(makerspace, machine))
    assert disabled.status_code == 400
    assert set(disabled.data) == {"module"}


def test_service_owned_and_unexpected_fields_are_rejected():
    makerspace, manager, machine, _ = make_machine_setup("maintenance-api-fields")
    response = authenticated_client(manager).post(
        log_url(makerspace, machine),
        {
            "summary": "No injection",
            "performed_by_id": manager.id,
            "machine_id": machine.id,
        },
        format="json",
    )
    assert response.status_code == 400
    assert not MaintenanceLog.objects.exists()

