import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts import rbac
from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.makerspaces import limits, role_services
from apps.makerspaces.models import Makerspace, MakerspaceMembership, MakerspaceRole


pytestmark = pytest.mark.django_db


def user(name, *, superadmin=False):
    return User.objects.create_user(
        username=name,
        password="password",
        access_status=User.AccessStatus.ACTIVE,
        role=User.Role.SUPERADMIN if superadmin else User.Role.REQUESTER,
        is_superuser=superadmin,
    )


def space(slug, **kwargs):
    return Makerspace.objects.create(name=slug, slug=slug, **kwargs)


def seeded(makerspace, legacy_role):
    return MakerspaceRole.objects.get(makerspace=makerspace, legacy_role=legacy_role)


def member(actor, makerspace, legacy_role=MakerspaceMembership.Role.SPACE_MANAGER):
    return MakerspaceMembership.objects.create(
        user=actor, makerspace=makerspace, role=legacy_role,
        assigned_role=seeded(makerspace, legacy_role),
    )


def client(actor):
    value = APIClient()
    value.force_authenticate(actor)
    return value


def list_url(makerspace):
    return reverse("admin-role-list-create", kwargs={"makerspace_id": makerspace.id})


def detail_url(makerspace, role):
    return reverse("admin-role-detail", kwargs={"makerspace_id": makerspace.id, "role_id": role.id})


def test_role_crud_catalog_and_audit():
    makerspace, actor = space("roles"), user("roles-manager")
    member(actor, makerspace)
    api = client(actor)
    assert api.get(list_url(makerspace)).status_code == 200
    created = api.post(list_url(makerspace), {"name": "Readers", "granted_actions": [rbac.Action.VIEW_INVENTORY]}, format="json")
    assert created.status_code == 201
    role = MakerspaceRole.objects.get(pk=created.data["id"])
    assert set(created.data) == {"id", "makerspace_id", "name", "slug", "granted_actions", "legacy_role", "is_default", "is_protected", "member_count", "created_at", "updated_at"}
    assert api.get(detail_url(makerspace, role)).status_code == 200
    patched = api.patch(detail_url(makerspace, role), {"name": "Readers renamed"}, format="json")
    assert patched.status_code == 200
    assert api.delete(detail_url(makerspace, role)).status_code == 204
    assert set(AuditLog.objects.filter(makerspace=makerspace).values_list("action", flat=True)) == {"role.created", "role.updated", "role.deleted"}
    catalog = api.get(reverse("admin-role-capabilities", kwargs={"makerspace_id": makerspace.id}))
    assert catalog.status_code == 200
    assert {"value", "label", "description", "group", "grantable", "lock_reason"} == set(catalog.data[0])
    assert not {rbac.Action.TRANSFER_STOCK, rbac.Action.MANAGE_STAFF} & {item["value"] for item in catalog.data}


def test_non_escalation_and_superadmin_policy():
    makerspace, actor = space("ceiling"), user("ceiling-manager")
    membership = member(actor, makerspace)
    membership.assigned_role.granted_actions.remove(rbac.Action.MANAGE_EVENTS)
    membership.assigned_role.save(update_fields=["granted_actions"])
    api = client(actor)
    base = {"name": "Nope", "granted_actions": [rbac.Action.MANAGE_MAKERSPACE]}
    assert api.post(list_url(makerspace), base, format="json").status_code == 403
    assert api.post(list_url(makerspace), {"name": "Events", "granted_actions": [rbac.Action.MANAGE_EVENTS]}, format="json").status_code == 403
    for action in (rbac.Action.TRANSFER_STOCK, rbac.Action.MANAGE_STAFF):
        response = api.post(list_url(makerspace), {"name": action, "granted_actions": [action]}, format="json")
        assert response.status_code == 400 and "granted_actions" in response.data
    root = user("role-root", superadmin=True)
    root_api = client(root)
    assert root_api.post(list_url(makerspace), {"name": "Governance", "granted_actions": [rbac.Action.MANAGE_MAKERSPACE]}, format="json").status_code == 201


def test_patch_protected_delete_and_scope_ordering():
    makerspace, actor = space("protected"), user("protected-manager")
    member(actor, makerspace)
    api = client(actor)
    core = seeded(makerspace, MakerspaceMembership.Role.SPACE_MANAGER)
    assert api.patch(detail_url(makerspace, core), {"name": "Operators"}, format="json").status_code == 200
    assert api.patch(detail_url(makerspace, core), {"granted_actions": core.granted_actions}, format="json").status_code == 403
    protected_delete = api.delete(detail_url(makerspace, core))
    assert protected_delete.status_code == 409 and protected_delete.data["code"] == "role_conflict"
    assigned = MakerspaceRole.objects.create(makerspace=makerspace, name="Assigned", slug="assigned", granted_actions=[])
    MakerspaceMembership.objects.create(user=user("assigned-user"), makerspace=makerspace, role="custom", assigned_role=assigned)
    assigned_delete = api.delete(detail_url(makerspace, assigned))
    assert assigned_delete.status_code == 409 and assigned_delete.data["code"] == "role_conflict"
    foreign = MakerspaceRole.objects.create(makerspace=space("foreign"), name="Foreign", slug="foreign", granted_actions=[])
    assert api.get(detail_url(makerspace, foreign)).status_code == 404
    assert client(user("outsider")).get(list_url(makerspace)).status_code == 404
    hidden = space("hidden", superadmin_access_enabled=False)
    assert client(user("hidden-root", superadmin=True)).get(list_url(hidden)).status_code == 404


def test_cap_is_managed_only_and_audit_failure_rolls_back(monkeypatch):
    makerspace, actor = space("cap", resource_limit_overrides={"custom_roles": 0}), user("cap-root", superadmin=True)
    api = client(actor)
    monkeypatch.setattr(limits, "is_self_host", lambda: False)
    response = api.post(list_url(makerspace), {"name": "Capped", "granted_actions": []}, format="json")
    assert response.status_code == 400 and response.data["limit"].code == "limit_reached"
    monkeypatch.setattr(limits, "is_self_host", lambda: True)
    assert api.post(list_url(makerspace), {"name": "Unlimited", "granted_actions": []}, format="json").status_code == 201
    monkeypatch.setattr(role_services.audit, "record", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("audit down")))
    with pytest.raises(RuntimeError):
        role_services.create_role(makerspace=makerspace, actor=actor, name="Rollback", granted_actions=[])
    assert not MakerspaceRole.objects.filter(makerspace=makerspace, name="Rollback").exists()
