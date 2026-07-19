from decimal import Decimal
from uuid import uuid4

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.machines.models import Machine, MachineServiceRequest, MachineType
from apps.machines.service_consumable_pools import create_pool
from apps.machines.service_workflow import submit
from apps.makerspaces.models import MakerspaceMembership
from tests.return_helpers import authenticated_client, make_member, make_space, make_user


pytestmark = pytest.mark.django_db


def make_machine(space, name="Service machine"):
    kind = MachineType.objects.create(
        makerspace=space, slug=f"service-api-{uuid4().hex[:8]}", name="Service API type"
    )
    return Machine.objects.create(makerspace=space, machine_type=kind, name=name)


def request_row(space, requester=None):
    requester = requester or make_member(f"service-requester-{uuid4().hex[:8]}", space)
    return submit(
        make_machine(space), requester, requester_name="Service member",
        contact_email=requester.email, contact_phone="123", title="Tune the machine",
    )


def list_url(space):
    return reverse("admin-machine-service-request-list-create", kwargs={"makerspace_id": space.pk})


def action_url(row, action):
    return reverse(f"admin-machine-service-request-{action}", kwargs={"pk": row.pk})


def test_manager_lists_scoped_queue_and_submits_for_member():
    space, other = make_space("service-api-list"), make_space("service-api-other")
    manager = make_member("service-api-manager", space, MakerspaceMembership.Role.MACHINE_MANAGER)
    member = make_member("service-api-member", space)
    own, foreign = request_row(space, member), request_row(other)
    client = authenticated_client(manager)

    listed = client.get(list_url(space))
    filtered = client.get(f"{list_url(space)}?status=pending&machine={own.bucket.machine_id}&bucket={own.bucket_id}")
    created = client.post(list_url(space), {
        "requester_id": member.pk, "machine_id": own.bucket.machine_id, "title": "Staff intake",
    }, format="json")

    assert listed.status_code == 200
    assert [row["id"] for row in listed.data] == [own.pk]
    assert [row["id"] for row in filtered.data] == [own.pk]
    assert created.status_code == 201
    assert created.data["requester"]["id"] == member.pk
    assert "object_key" not in str(created.data)
    assert client.get(reverse("admin-machine-service-request-detail", kwargs={"pk": foreign.pk})).status_code == 404


def test_manager_can_run_lifecycle_and_invalid_edge_is_conflict():
    space = make_space("service-api-lifecycle")
    manager = make_member("service-api-lifecycle-manager", space, MakerspaceMembership.Role.MACHINE_MANAGER)
    member = make_member("service-api-lifecycle-member", space)
    row = request_row(space, member)
    client = authenticated_client(manager)

    assert client.post(action_url(row, "accept"), {"estimated_minutes": 15}, format="json").status_code == 200
    assert client.post(action_url(row, "start"), {"machine_id": row.bucket.machine_id}, format="json").status_code == 200
    assert client.post(action_url(row, "complete"), {"actual_minutes": 12, "consumptions": []}, format="json").status_code == 200
    assert client.post(action_url(row, "collect"), {}, format="json").status_code == 200
    response = client.post(action_url(row, "accept"), {}, format="json")
    row.refresh_from_db()
    assert row.status == MachineServiceRequest.Status.COLLECTED
    assert (response.status_code, response.data["code"]) == (409, "service_invalid_transition")


def test_start_endpoint_reserves_requested_consumable_grams():
    space = make_space("service-api-pool-reserve")
    manager = make_member("service-api-pool-reserve-manager", space, MakerspaceMembership.Role.MACHINE_MANAGER)
    row = request_row(space)
    pool = create_pool(space, manager, material="PLA", initial_grams="50", machine=row.bucket.machine)
    client = authenticated_client(manager)

    assert client.post(action_url(row, "accept"), {}, format="json").status_code == 200
    response = client.post(action_url(row, "start"), {
        "machine_id": row.bucket.machine_id,
        "consumable_pool_id": pool.pk,
        "planned_grams": "12.50",
    }, format="json")

    row.refresh_from_db(); pool.refresh_from_db()
    assert response.status_code == 200
    assert (row.run_consumable_pool_id, row.reserved_grams, pool.remaining_grams) == (pool.pk, Decimal("12.50"), Decimal("37.50"))


def test_manager_can_reject_and_fail_a_service_request():
    space = make_space("service-api-terminal-actions")
    manager = make_member("service-api-terminal-manager", space, MakerspaceMembership.Role.MACHINE_MANAGER)
    client = authenticated_client(manager)
    rejected, failed = request_row(space), request_row(space)

    assert client.post(action_url(rejected, "reject"), {"reason": "Unsupported"}, format="json").status_code == 200
    assert client.post(action_url(failed, "accept"), {}, format="json").status_code == 200
    assert client.post(action_url(failed, "start"), {"machine_id": failed.bucket.machine_id}, format="json").status_code == 200
    response = client.post(action_url(failed, "fail"), {
        "reason": "Interrupted", "percent_complete": 25, "actual_minutes": 4, "consumptions": [],
    }, format="json")

    rejected.refresh_from_db(); failed.refresh_from_db()
    assert rejected.status == MachineServiceRequest.Status.REJECTED
    assert (response.status_code, failed.status) == (200, MachineServiceRequest.Status.FAILED)


def test_wrong_role_is_forbidden_and_disabled_module_is_rejected():
    space = make_space("service-api-permission")
    manager = make_member("service-api-permission-manager", space, MakerspaceMembership.Role.MACHINE_MANAGER)
    guest = make_member(
        "service-api-permission-guest", space,
        MakerspaceMembership.Role.GUEST_ADMIN, User.Role.GUEST_ADMIN,
    )
    row = request_row(space)
    assert authenticated_client(guest).get(list_url(space)).status_code == 403
    space.enabled_modules = [item for item in space.enabled_modules if item != "machine_service"]
    space.save(update_fields=["enabled_modules"])
    assert authenticated_client(manager).get(list_url(space)).status_code == 400
    assert authenticated_client(manager).get(
        reverse("admin-machine-service-request-detail", kwargs={"pk": row.pk})
    ).status_code == 400
