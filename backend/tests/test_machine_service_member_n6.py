from uuid import uuid4

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.machines.models import Machine, MachineServiceRequest, MachineType
from apps.makerspaces.models import Makerspace, MakerspaceMembership, MakerspaceRole
from apps.makerspaces.waiver_services import accept_waiver, publish_waiver
from apps.presence import services as presence


pytestmark = pytest.mark.django_db


def member(space, username):
    user = User.objects.create_user(
        username=username,
        display_name=f"{username} display",
        email=f"{username}@example.test",
        phone="+15550000000",
    )
    MakerspaceMembership.objects.create(
        makerspace=space,
        user=user,
        assigned_role=MakerspaceRole.objects.get(makerspace=space, slug="member"),
        role="custom",
    )
    return user


def api_client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def machine(space, *, public=True):
    machine_type = MachineType.objects.create(
        makerspace=space,
        slug=f"member-service-{uuid4().hex[:8]}",
        name="Member service",
    )
    return Machine.objects.create(
        makerspace=space,
        machine_type=machine_type,
        name="Laser cutter",
        is_public=public,
    )


def submit_url(space):
    return f"/api/v1/public/{space.slug}/machine-service-requests"


def payload(target, **extra):
    return {"machine_id": target.id, "title": "Tune optics", **extra}


def eligible(space, username="member"):
    user = member(space, username)
    presence.start_session(user, space, 60)
    return user


def recursive_values(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from recursive_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from recursive_values(item)
    else:
        yield str(value)


def test_member_submit_requires_authentication_membership_waiver_and_presence():
    space, target = Makerspace.objects.create(name="N6 gate", slug="n6-gate"), None
    target = machine(space)
    assert APIClient().post(submit_url(space), payload(target), format="json").status_code == 401

    outsider = User.objects.create_user(username="n6-outsider")
    denied = api_client(outsider).post(submit_url(space), payload(target), format="json")
    assert denied.status_code == 403 and denied.data["code"] == "membership_required"

    user = member(space, "n6-waiver")
    membership = user.makerspace_memberships.get(makerspace=space)
    publish_waiver(user, space, "Terms", "v1")
    waiver = api_client(user).post(submit_url(space), payload(target), format="json")
    assert waiver.status_code == 403 and waiver.data["code"] == "waiver_acceptance_required"
    accept_waiver(membership)
    absent = api_client(user).post(submit_url(space), payload(target), format="json")
    assert absent.status_code == 403 and absent.data["code"] == "presence_required"


def test_member_submit_snapshots_account_identity_and_honeypot_is_a_noop():
    space, target = Makerspace.objects.create(name="N6 submit", slug="n6-submit"), None
    target, user = machine(space), eligible(space, "n6-owner")
    before = MachineServiceRequest.objects.count()
    decoy = api_client(user).post(submit_url(space), {"website": "bot"}, format="json")
    assert decoy.status_code == 201 and MachineServiceRequest.objects.count() == before

    response = api_client(user).post(submit_url(space), payload(
        target,
        requester_name="forged",
        contact_email="forged@example.test",
        contact_phone="forged",
    ), format="json")
    assert response.status_code == 201
    row = MachineServiceRequest.objects.get()
    assert (row.member, row.requester, row.requester_name, row.contact_email, row.contact_phone) == (
        user, user, user.display_name, user.email, user.phone,
    )
    assert AuditLog.objects.filter(target_id=str(row.pk), action="machine_service.submitted").exists()
    assert not set(recursive_values(response.data)) & {user.email, user.phone, str(user.pk)}


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me", INFRA_HOSTS={"testserver"})
def test_member_submit_enforces_both_managed_caps():
    open_space = Makerspace.objects.create(
        name="N6 open cap", slug="n6-open-cap",
        resource_limit_overrides={"machine_service_open": 0, "machine_service_submit": 10},
    )
    response = api_client(eligible(open_space, "n6-open-user")).post(
        submit_url(open_space), payload(machine(open_space)), format="json", HTTP_HOST="testserver",
    )
    assert response.status_code == 400 and "limit" in response.data

    daily_space = Makerspace.objects.create(
        name="N6 daily cap", slug="n6-daily-cap",
        resource_limit_overrides={"machine_service_open": 10, "machine_service_submit": 0},
    )
    response = api_client(eligible(daily_space, "n6-daily-user")).post(
        submit_url(daily_space), payload(machine(daily_space)), format="json", HTTP_HOST="testserver",
    )
    assert response.status_code == 400 and "limit" in response.data


def test_member_submit_hides_other_tenant_machine_and_disabled_module_blocks():
    space = Makerspace.objects.create(name="N6 scope", slug="n6-scope")
    other_space = Makerspace.objects.create(name="N6 other", slug="n6-other")
    other_machine = machine(other_space)
    response = api_client(eligible(space, "n6-scope-user")).post(
        submit_url(space), payload(other_machine), format="json",
    )
    assert response.status_code == 404

    space.enabled_modules = [key for key in space.enabled_modules if key != "machine_service"]
    space.save(update_fields=["enabled_modules"])
    response = api_client(eligible(space, "n6-module-user")).post(
        submit_url(space), payload(machine(space)), format="json",
    )
    assert response.status_code == 400


def test_member_activity_is_owned_by_member_and_uses_service_queue_projection():
    space = Makerspace.objects.create(name="N6 activity", slug="n6-activity")
    target = machine(space)
    owner, other = eligible(space, "n6-activity-owner"), eligible(space, "n6-activity-other")
    own = MachineServiceRequest.objects.create(
        bucket=target.service_buckets.create(name="Service Requests"),
        requester=owner,
        member=owner,
        title="Own pending",
    )
    MachineServiceRequest.objects.create(
        bucket=own.bucket,
        requester=other,
        member=other,
        title="Other accepted",
        status=MachineServiceRequest.Status.ACCEPTED,
    )
    legacy = MachineServiceRequest.objects.create(
        bucket=own.bucket,
        requester=owner,
        title="Legacy requester-only",
    )

    response = api_client(owner).get(f"/api/v1/member/makerspaces/{space.id}/activity")
    assert response.status_code == 200
    assert response.data["machine_service_requests"] == [{
        "title": own.title,
        "status": "pending",
        "created_at": response.data["machine_service_requests"][0]["created_at"],
        "queue_position": 2,
    }]
    serialized = str(response.data["machine_service_requests"])
    assert all(value not in serialized for value in (other.email, other.phone, "contact_email", "object_key"))
