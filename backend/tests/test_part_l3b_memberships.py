import pytest
from django.urls import reverse

from apps.accounts import rbac
from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.makerspaces import limits
from apps.makerspaces.models import MakerspaceMembership, MakerspaceRole
from tests.return_helpers import authenticated_client, make_member, make_space, make_user


pytestmark = pytest.mark.django_db


def seeded(makerspace, legacy_role):
    return MakerspaceRole.objects.get(
        makerspace=makerspace, legacy_role=legacy_role
    )


def root(username):
    return make_user(
        username,
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )


def membership_url(makerspace):
    return reverse(
        "admin-membership-list-create", kwargs={"makerspace_id": makerspace.id}
    )


def assign_url(makerspace, membership):
    return reverse(
        "admin-membership-role-assign",
        kwargs={"makerspace_id": makerspace.id, "membership_id": membership.id},
    )


def test_generic_create_syncs_custom_and_default_roles():
    makerspace, actor = make_space("l3b-create"), root("l3b-create-root")
    api = authenticated_client(actor)
    custom = MakerspaceRole.objects.create(
        makerspace=makerspace,
        name="Readers",
        slug="readers",
        granted_actions=[rbac.Action.VIEW_INVENTORY],
    )

    created = api.post(
        membership_url(makerspace),
        {"username": "l3b-custom", "role_id": custom.id},
        format="json",
    )
    assert created.status_code == 201
    membership = MakerspaceMembership.objects.select_related("assigned_role").get(
        pk=created.data["id"]
    )
    assert membership.role == MakerspaceMembership.Role.CUSTOM
    assert membership.assigned_role == custom
    assert rbac.effective_actions(membership.user, makerspace.id) == {
        rbac.Action.VIEW_INVENTORY
    }

    default = seeded(makerspace, MakerspaceMembership.Role.MACHINE_MANAGER)
    default_created = api.post(
        membership_url(makerspace),
        {"username": "l3b-default", "role_id": default.id},
        format="json",
    )
    assert default_created.status_code == 201
    default_membership = MakerspaceMembership.objects.get(pk=default_created.data["id"])
    assert default_membership.assigned_role == default
    assert default_membership.role == MakerspaceMembership.Role.MACHINE_MANAGER


def test_membership_scope_ordering_and_assignment_audit():
    makerspace, foreign = make_space("l3b-scope"), make_space("l3b-foreign")
    actor, target = root("l3b-scope-root"), make_user(
        "l3b-scope-target", access_status=User.AccessStatus.ACTIVE
    )
    membership = MakerspaceMembership.objects.create(user=target, makerspace=makerspace)
    api = authenticated_client(actor)
    custom = MakerspaceRole.objects.create(
        makerspace=makerspace,
        name="Inventory readers",
        slug="inventory-readers",
        granted_actions=[rbac.Action.VIEW_INVENTORY],
    )
    foreign_role = MakerspaceRole.objects.create(
        makerspace=foreign, name="Foreign", slug="foreign", granted_actions=[]
    )

    assert api.post(
        membership_url(makerspace),
        {"username": "l3b-foreign-role", "role_id": foreign_role.id},
        format="json",
    ).status_code == 404
    foreign_membership = MakerspaceMembership.objects.create(
        user=make_user("l3b-foreign-member", access_status=User.AccessStatus.ACTIVE),
        makerspace=foreign,
    )
    assert api.patch(
        assign_url(makerspace, foreign_membership), {"role_id": custom.id}, format="json"
    ).status_code == 404

    patched = api.patch(
        assign_url(makerspace, membership), {"role_id": custom.id}, format="json"
    )
    assert patched.status_code == 200
    membership.refresh_from_db()
    assert membership.assigned_role == custom
    assert membership.role == MakerspaceMembership.Role.CUSTOM
    assert AuditLog.objects.filter(
        action="staff.role_assigned", makerspace=makerspace, target_id=str(target.id)
    ).exists()

    outsider = authenticated_client(
        make_user("l3b-outsider", access_status=User.AccessStatus.ACTIVE)
    )
    assert outsider.get(membership_url(makerspace)).status_code == 404
    non_manager = make_member(
        "l3b-non-manager", makerspace,
        membership_role=MakerspaceMembership.Role.PRINT_MANAGER,
        role=User.Role.REQUESTER,
    )
    assert authenticated_client(non_manager).get(membership_url(makerspace)).status_code == 403
    makerspace.archived_at = "2024-01-01T00:00:00Z"
    makerspace.save(update_fields=["archived_at"])
    assert api.get(membership_url(makerspace)).status_code == 404
    hidden = make_space("l3b-hidden")
    hidden.superadmin_access_enabled = False
    hidden.save(update_fields=["superadmin_access_enabled"])
    assert api.get(membership_url(hidden)).status_code == 404


def test_dynamic_assignment_and_revoke_authority():
    makerspace = make_space("l3b-authority")
    manager = make_member("l3b-manager", makerspace)
    target = make_user("l3b-target", access_status=User.AccessStatus.ACTIVE)
    protected = MakerspaceMembership.objects.create(
        user=target,
        makerspace=makerspace,
        role=MakerspaceMembership.Role.SPACE_MANAGER,
        assigned_role=seeded(makerspace, MakerspaceMembership.Role.SPACE_MANAGER),
    )
    governance = MakerspaceRole.objects.create(
        makerspace=makerspace,
        name="Governance",
        slug="governance",
        granted_actions=[rbac.Action.MANAGE_MAKERSPACE],
    )
    manager_membership = MakerspaceMembership.objects.get(
        makerspace=makerspace, user=manager
    )
    manager_membership.assigned_role = seeded(
        makerspace, MakerspaceMembership.Role.SPACE_MANAGER
    )
    manager_membership.save(update_fields=["assigned_role"])
    manager_membership.assigned_role.granted_actions = [
        action
        for action in manager_membership.assigned_role.granted_actions
        if action != rbac.Action.MANAGE_EVENTS
    ]
    manager_membership.assigned_role.save(update_fields=["granted_actions"])
    events = MakerspaceRole.objects.create(
        makerspace=makerspace,
        name="Events",
        slug="events",
        granted_actions=[rbac.Action.MANAGE_EVENTS],
    )
    manager_api = authenticated_client(manager)
    assert manager_api.post(
        membership_url(makerspace),
        {"username": "l3b-escalate", "role_id": governance.id},
        format="json",
    ).status_code == 403
    assert manager_api.post(
        membership_url(makerspace),
        {"username": "l3b-beyond-ceiling", "role_id": events.id},
        format="json",
    ).status_code == 403
    assert manager_api.patch(
        assign_url(makerspace, protected), {"role_id": seeded(makerspace, MakerspaceMembership.Role.MACHINE_MANAGER).id},
        format="json",
    ).status_code == 403
    assert manager_api.delete(
        reverse("admin-membership-revoke", kwargs={"pk": protected.id})
    ).status_code == 403

    root_api = authenticated_client(root("l3b-root"))
    assert root_api.patch(
        assign_url(makerspace, protected), {"role_id": governance.id}, format="json"
    ).status_code == 200
    delegated = MakerspaceMembership.objects.create(
        user=make_user("l3b-delegated", access_status=User.AccessStatus.ACTIVE),
        makerspace=makerspace,
        role=MakerspaceMembership.Role.MACHINE_MANAGER,
        assigned_role=seeded(makerspace, MakerspaceMembership.Role.MACHINE_MANAGER),
    )
    assert manager_api.delete(
        reverse("admin-membership-revoke", kwargs={"pk": delegated.id})
    ).status_code == 204
    assert root_api.delete(
        reverse("admin-membership-revoke", kwargs={"pk": protected.id})
    ).status_code == 204
    hidden = make_space("l3b-hidden-revoke")
    hidden.superadmin_access_enabled = False
    hidden.save(update_fields=["superadmin_access_enabled"])
    hidden_membership = MakerspaceMembership.objects.create(
        user=make_user("l3b-hidden-target", access_status=User.AccessStatus.ACTIVE),
        makerspace=hidden,
    )
    assert root_api.delete(
        reverse("admin-membership-revoke", kwargs={"pk": hidden_membership.id})
    ).status_code == 404


def test_legacy_create_writes_default_assignment_and_quota_rolls_back(monkeypatch):
    makerspace, actor = make_space("l3b-legacy"), root("l3b-legacy-root")
    api = authenticated_client(actor)
    created = api.post(
        reverse("admin-users-space-managers"),
        {
            "username": "l3b-legacy-manager",
            "makerspace_id": makerspace.id,
            "role": MakerspaceMembership.Role.SPACE_MANAGER,
        },
        format="json",
    )
    assert created.status_code == 201
    membership = MakerspaceMembership.objects.select_related("assigned_role").get(
        pk=created.data["id"]
    )
    assert membership.assigned_role.legacy_role == MakerspaceMembership.Role.SPACE_MANAGER

    capped = make_space("l3b-cap")
    capped.resource_limit_overrides = {"staff": 0}
    capped.save(update_fields=["resource_limit_overrides"])
    monkeypatch.setattr(limits, "is_self_host", lambda: False)
    rejected = api.post(
        membership_url(capped),
        {"username": "l3b-no-orphan", "role_id": seeded(capped, MakerspaceMembership.Role.MACHINE_MANAGER).id},
        format="json",
    )
    assert rejected.status_code == 400
    assert not User.objects.filter(username="l3b-no-orphan").exists()


def test_attaching_existing_account_preserves_global_role():
    # P1: attaching an EXISTING account to a makerspace role must never rewrite its global
    # User.role — otherwise a manager could add a known non-is_superuser global superadmin as
    # a delegable/custom role and silently strip their global authority.
    makerspace = make_space("l3b-global-role")
    manager = make_member("l3b-gr-manager", makerspace)
    manager_membership = MakerspaceMembership.objects.get(makerspace=makerspace, user=manager)
    manager_membership.assigned_role = seeded(
        makerspace, MakerspaceMembership.Role.SPACE_MANAGER
    )
    manager_membership.save(update_fields=["assigned_role"])
    victim = make_user(
        "l3b-hidden-superadmin",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )
    readers = MakerspaceRole.objects.create(
        makerspace=makerspace,
        name="Readers",
        slug="gr-readers",
        granted_actions=[rbac.Action.VIEW_INVENTORY],
    )
    resp = authenticated_client(manager).post(
        membership_url(makerspace),
        {"username": victim.username, "role_id": readers.id},
        format="json",
    )
    assert resp.status_code == 201
    victim.refresh_from_db()
    assert victim.role == User.Role.SUPERADMIN


def test_oversized_account_field_is_a_clean_400():
    # P2: an oversized username must be a validation error, not a DB DataError -> 500.
    makerspace, actor = make_space("l3b-oversize"), root("l3b-oversize-root")
    readers = MakerspaceRole.objects.create(
        makerspace=makerspace,
        name="Readers",
        slug="oversize-readers",
        granted_actions=[rbac.Action.VIEW_INVENTORY],
    )
    resp = authenticated_client(actor).post(
        membership_url(makerspace),
        {"username": "x" * 151, "role_id": readers.id},
        format="json",
    )
    assert resp.status_code == 400
    assert not User.objects.filter(username="x" * 151).exists()
