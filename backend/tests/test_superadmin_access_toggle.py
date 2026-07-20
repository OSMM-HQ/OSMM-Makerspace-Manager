import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.audit import services as audit
from apps.makerspaces.models import MakerspaceMembership
from tests.return_helpers import (
    authenticated_client,
    make_issued_request,
    make_member,
    make_product,
    make_space,
    make_user,
)

pytestmark = pytest.mark.django_db


def make_superadmin(username):
    return make_user(
        username,
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )


def makerspace_detail_url(makerspace):
    return reverse("admin-makerspace", kwargs={"pk": makerspace.id})


def test_superadmin_cannot_re_enable_but_makerspace_admin_can():
    space = make_space("access-toggle")
    space_manager = make_member("access-toggle-manager", space)
    superadmin = make_superadmin("access-toggle-super")

    # Disabling superadmin access now requires a usable instance Platform Email
    # (so locked-out staff always have a forgot-password recovery path).
    from apps.integrations.models import PlatformEmailSettings

    cfg = PlatformEmailSettings.load()
    cfg.smtp_host = "smtp.example.com"
    cfg.save(update_fields=["smtp_host"])

    disabled = authenticated_client(superadmin).patch(
        makerspace_detail_url(space),
        {"superadmin_access_enabled": False},
        format="json",
    )
    assert disabled.status_code == 200
    space.refresh_from_db()
    assert space.superadmin_access_enabled is False

    # Hard hide: once disabled, the space is RBAC-invisible to the superadmin, so
    # the re-enable PATCH 404s (it can't resolve the object) — re-enable stays a
    # space-manager-only right, now enforced even harder than the old 400.
    regrant = authenticated_client(superadmin).patch(
        makerspace_detail_url(space),
        {"superadmin_access_enabled": True},
        format="json",
    )
    assert regrant.status_code == 404
    space.refresh_from_db()
    assert space.superadmin_access_enabled is False

    restored = authenticated_client(space_manager).patch(
        makerspace_detail_url(space),
        {"superadmin_access_enabled": True},
        format="json",
    )
    assert restored.status_code == 200
    space.refresh_from_db()
    assert space.superadmin_access_enabled is True


def test_superadmin_aggregates_hide_disabled_space():
    hidden_space = make_space("access-hidden-aggregate")
    hidden_space.superadmin_access_enabled = False
    hidden_space.save(update_fields=["superadmin_access_enabled"])
    visible_space = make_space("access-visible-aggregate")
    hidden_actor = make_member("access-hidden-issuer", hidden_space)
    visible_actor = make_member("access-visible-issuer", visible_space)
    superadmin = make_superadmin("access-aggregate-super")

    hidden_product = make_product(hidden_space, name="Hidden Scope")
    visible_product = make_product(visible_space, name="Visible Scope")
    make_issued_request(hidden_space, hidden_actor, [(hidden_product, 1)])
    make_issued_request(visible_space, visible_actor, [(visible_product, 1)])

    client = authenticated_client(superadmin)
    summary = client.get(reverse("analytics-aggregate", kwargs={"report_key": "summary"}))
    ledger = client.get(reverse("ledger-aggregate"))

    assert summary.status_code == 200
    assert summary.data["products"] == 1
    assert summary.data["active_loans"] == 1
    assert summary.data["issued_quantity"] == 1
    assert ledger.status_code == 200
    assert ledger.data["count"] == 1
    assert {row["makerspace_id"] for row in ledger.data["results"]} == {visible_space.id}

def test_superadmin_cannot_reach_disabled_space_per_makerspace_reports():
    hidden_space = make_space("access-hidden-direct")
    make_member("access-hidden-direct-manager", hidden_space)
    hidden_space.superadmin_access_enabled = False
    hidden_space.save(update_fields=["superadmin_access_enabled"])
    superadmin = make_superadmin("access-direct-super")
    client = authenticated_client(superadmin)

    # The aggregate paths already drop hidden spaces; the per-makerspace endpoints must
    # also refuse a direct-by-id query from a superadmin (soft-hide → 404, not data).
    assert client.get(
        reverse("ledger", kwargs={"makerspace_id": hidden_space.id})
    ).status_code == 404
    assert client.get(
        reverse("analytics-summary", kwargs={"makerspace_id": hidden_space.id})
    ).status_code == 404
    assert client.get(
        reverse(
            "report-export",
            kwargs={"makerspace_id": hidden_space.id, "report_key": "summary"},
        )
    ).status_code == 404


def test_disabled_space_own_manager_still_sees_its_reports():
    hidden_space = make_space("access-hidden-own")
    hidden_space.superadmin_access_enabled = False
    hidden_space.save(update_fields=["superadmin_access_enabled"])
    space_manager = make_member("access-hidden-own-manager", hidden_space)

    # Soft-hide is superadmin-only: the space's own Space Manager keeps full report access.
    response = authenticated_client(space_manager).get(
        reverse("analytics-summary", kwargs={"makerspace_id": hidden_space.id})
    )
    assert response.status_code == 200


def test_audit_list_hides_disabled_space_even_with_explicit_filter():
    hidden_space = make_space("access-hidden-audit")
    hidden_space.superadmin_access_enabled = False
    hidden_space.save(update_fields=["superadmin_access_enabled"])
    actor = make_member("access-hidden-audit-actor", hidden_space)
    superadmin = make_superadmin("access-audit-super")
    audit.record(
        actor,
        "makerspace.hidden_test",
        makerspace=hidden_space,
        target=hidden_space,
    )

    response = authenticated_client(superadmin).get(
        f"{reverse('admin-audit-logs')}?makerspace={hidden_space.id}"
    )

    assert response.status_code == 200
    assert response.data["results"] == []


def test_makerspace_list_excludes_disabled_space_for_superadmin():
    hidden_space = make_space("access-hidden-list")
    make_member("access-hidden-list-manager", hidden_space)
    hidden_space.superadmin_access_enabled = False
    hidden_space.save(update_fields=["superadmin_access_enabled"])
    visible_space = make_space("access-visible-list")
    superadmin = make_superadmin("access-list-super")

    response = authenticated_client(superadmin).get(reverse("admin-makerspaces"))
    detail = authenticated_client(superadmin).get(makerspace_detail_url(hidden_space))

    assert response.status_code == 200
    rows = {row["id"]: row for row in response.data}
    assert hidden_space.id not in rows
    assert "public_api_key" in rows[visible_space.id]
    assert detail.status_code == 404


def test_member_of_disabled_space_unaffected():
    hidden_space = make_space("access-hidden-member")
    hidden_space.superadmin_access_enabled = False
    hidden_space.save(update_fields=["superadmin_access_enabled"])
    space_manager = make_member(
        "access-hidden-member-manager",
        hidden_space,
        membership_role=MakerspaceMembership.Role.SPACE_MANAGER,
        role=User.Role.SPACE_MANAGER,
    )

    response = authenticated_client(space_manager).get(reverse("admin-makerspaces"))

    assert response.status_code == 200
    rows = {row["id"]: row for row in response.data}
    assert set(rows) == {hidden_space.id}
    assert rows[hidden_space.id]["superadmin_access_enabled"] is False
    assert "public_api_key" in rows[hidden_space.id]
