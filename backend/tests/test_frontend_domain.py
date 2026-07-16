import importlib

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.makerspaces.models import Makerspace
from apps.makerspaces.platform import makerspace_staff_origins
from tests.return_helpers import authenticated_client, make_member, make_space, make_user

pytestmark = pytest.mark.django_db


def _superadmin(username):
    return make_user(
        username,
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
        is_staff=True,
        is_superuser=True,
    )

# The data migration's host-resolution logic is pure (no ORM) so its fail-loud
# branches are unit-testable without a migration rewind.
_host_migration = importlib.import_module(
    "apps.makerspaces.migrations.0016_migrate_tenant_frontend_hosts"
)


def makerspace_detail_url(makerspace):
    return reverse("admin-makerspace", kwargs={"pk": makerspace.id})


def test_makerspace_save_normalizes_frontend_domain():
    makerspace = Makerspace.objects.create(
        name="Alpha",
        slug="frontend-normalize-alpha",
        frontend_domain="  Alpha.COM ",
    )

    assert makerspace.frontend_domain == "alpha.com"

    makerspace.frontend_domain = ""
    makerspace.save(update_fields=["frontend_domain"])

    assert makerspace.frontend_domain is None


def test_makerspace_frontend_domain_is_unique_case_insensitively():
    with pytest.raises(IntegrityError), transaction.atomic():
        Makerspace.objects.bulk_create(
            [
                Makerspace(
                    name="Alpha",
                    slug="frontend-ci-alpha",
                    public_code="CIA1",
                    frontend_domain="alpha.com",
                ),
                Makerspace(
                    name="Alpha Duplicate",
                    slug="frontend-ci-alpha-dupe",
                    public_code="CIA2",
                    frontend_domain="Alpha.com",
                ),
            ]
        )


def test_many_makerspaces_can_have_null_frontend_domain():
    first = make_space("frontend-null-one")
    second = make_space("frontend-null-two")

    assert first.frontend_domain is None
    assert second.frontend_domain is None


def test_hidden_from_central_directory_requires_frontend_domain_in_model_validation():
    makerspace = Makerspace(
        name="Hidden",
        slug="frontend-hidden-invalid",
        hidden_from_central_directory=True,
    )

    with pytest.raises(ValidationError):
        makerspace.full_clean()


def test_hidden_from_central_directory_requires_frontend_domain_in_database():
    makerspace = make_space("frontend-hidden-db-invalid")

    with pytest.raises(IntegrityError), transaction.atomic():
        Makerspace.objects.filter(pk=makerspace.pk).update(
            hidden_from_central_directory=True,
            frontend_domain=None,
        )


def test_serializer_rejects_hiding_without_effective_frontend_domain():
    makerspace = make_space("frontend-api-hidden-invalid")
    manager = make_member("frontend-api-hidden-invalid-manager", makerspace)

    response = authenticated_client(manager).patch(
        makerspace_detail_url(makerspace),
        {"hidden_from_central_directory": True},
        format="json",
    )

    assert response.status_code == 400
    makerspace.refresh_from_db()
    assert makerspace.hidden_from_central_directory is False


def test_serializer_clearing_frontend_domain_also_unhides_makerspace():
    makerspace = make_space("frontend-api-clear")
    makerspace.frontend_domain = "alpha.example.com"
    makerspace.hidden_from_central_directory = True
    makerspace.save(update_fields=["frontend_domain", "hidden_from_central_directory"])
    manager = make_member("frontend-api-clear-manager", makerspace)

    response = authenticated_client(manager).patch(
        makerspace_detail_url(makerspace),
        {"frontend_domain": ""},
        format="json",
    )

    assert response.status_code == 200
    makerspace.refresh_from_db()
    assert makerspace.frontend_domain is None
    assert makerspace.hidden_from_central_directory is False


def test_serializer_rejects_duplicate_frontend_domain_case_insensitively():
    existing = make_space("frontend-api-existing")
    existing.frontend_domain = "alpha.example.com"
    existing.save(update_fields=["frontend_domain"])
    target = make_space("frontend-api-target")
    # Self-host default: use a superadmin so the duplicate rule (not the A2 gate) is exercised.
    superadmin = _superadmin("frontend-api-target-superadmin")

    response = authenticated_client(superadmin).patch(
        makerspace_detail_url(target),
        {"frontend_domain": " Alpha.EXAMPLE.com "},
        format="json",
    )

    assert response.status_code == 400
    assert "frontend_domain" in response.data
    target.refresh_from_db()
    assert target.frontend_domain is None


def test_migration_resolves_single_host_per_makerspace():
    rows = [
        (1, "Alpha.COM", []),
        (1, None, ["https://alpha.com/"]),  # same host (case/path/origin) dedupes
        (2, None, ["https://beta.com"]),
    ]

    assert _host_migration.resolve_frontend_domains(rows) == {
        1: "alpha.com",
        2: "beta.com",
    }


def test_migration_raises_on_ambiguous_hosts_for_one_makerspace():
    with pytest.raises(RuntimeError):
        _host_migration.resolve_frontend_domains([(1, "a.com", []), (1, None, ["https://b.com"])])


def test_migration_raises_on_cross_makerspace_host_collision():
    with pytest.raises(RuntimeError):
        _host_migration.resolve_frontend_domains([(1, "x.com", []), (2, "x.com", [])])


def test_migration_raises_on_invalid_origin():
    with pytest.raises(RuntimeError):
        _host_migration.resolve_frontend_domains([(1, None, ["not-a-url"])])
    with pytest.raises(RuntimeError):
        _host_migration.resolve_frontend_domains([(1, None, ["https://host/some/path"])])


def test_migration_skips_makerspace_without_hosts():
    assert _host_migration.resolve_frontend_domains([(1, None, [])]) == {}


def test_save_normalizes_pasted_url_to_bare_host():
    makerspace = Makerspace.objects.create(
        name="Pasted",
        slug="frontend-pasted-url",
        frontend_domain="https://Alpha.Example/admin",
    )

    assert makerspace.frontend_domain == "alpha.example"


def test_serializer_normalizes_pasted_url_and_rejects_garbage():
    # Self-host default: only a superadmin may set the custom domain (Task A2).
    makerspace = make_space("frontend-api-normalize")
    client = authenticated_client(_superadmin("frontend-api-normalize-superadmin"))

    ok = client.patch(
        makerspace_detail_url(makerspace),
        {"frontend_domain": "https://Branded.Example/admin"},
        format="json",
    )
    assert ok.status_code == 200
    makerspace.refresh_from_db()
    assert makerspace.frontend_domain == "branded.example"

    bad = client.patch(
        makerspace_detail_url(makerspace),
        {"frontend_domain": "not a domain"},
        format="json",
    )
    assert bad.status_code == 400
    assert "frontend_domain" in bad.data


# --- Part A / Task A2: superadmin-only self-host custom domain, auto-verified ----


@override_settings(PLATFORM_DOMAIN_SUFFIX="")
def test_selfhost_superadmin_patch_domain_verifies_and_trusts_origin():
    makerspace = make_space("a2-selfhost-superadmin")
    superadmin = _superadmin("a2-selfhost-superadmin-user")

    response = authenticated_client(superadmin).patch(
        makerspace_detail_url(makerspace),
        {"frontend_domain": "alpha.example.com"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["frontend_domain_status"] == Makerspace.DomainStatus.VERIFIED
    assert response.data["domain_verified_at"] is not None
    makerspace.refresh_from_db()
    assert makerspace.frontend_domain == "alpha.example.com"
    assert makerspace.frontend_domain_status == Makerspace.DomainStatus.VERIFIED
    assert "https://alpha.example.com" in makerspace_staff_origins(makerspace)


@override_settings(PLATFORM_DOMAIN_SUFFIX="")
def test_selfhost_non_superadmin_cannot_set_domain():
    makerspace = make_space("a2-selfhost-nonsuper")
    manager = make_member("a2-selfhost-nonsuper-manager", makerspace)

    response = authenticated_client(manager).patch(
        makerspace_detail_url(makerspace),
        {"frontend_domain": "evil.example.com"},
        format="json",
    )

    assert response.status_code == 400
    assert "frontend_domain" in response.data
    makerspace.refresh_from_db()
    assert makerspace.frontend_domain in (None, "")


@override_settings(PLATFORM_DOMAIN_SUFFIX="")
def test_selfhost_non_superadmin_noop_domain_patch_is_allowed():
    # A non-superadmin PATCH that doesn't change frontend_domain must still succeed.
    makerspace = make_space("a2-selfhost-noop")
    makerspace.frontend_domain = "kept.example.com"
    makerspace.frontend_domain_status = Makerspace.DomainStatus.VERIFIED
    makerspace.save(update_fields=["frontend_domain", "frontend_domain_status"])
    manager = make_member("a2-selfhost-noop-manager", makerspace)

    response = authenticated_client(manager).patch(
        makerspace_detail_url(makerspace),
        {"frontend_domain": "kept.example.com", "default_loan_days": 9},
        format="json",
    )

    assert response.status_code == 200
    makerspace.refresh_from_db()
    assert makerspace.frontend_domain == "kept.example.com"
    assert makerspace.default_loan_days == 9


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me")
def test_managed_patch_custom_domain_stays_pending():
    makerspace = make_space("a2-managed-pending")
    superadmin = _superadmin("a2-managed-pending-user")

    response = authenticated_client(superadmin).patch(
        makerspace_detail_url(makerspace),
        {"frontend_domain": "beta.example.com"},
        format="json",
        HTTP_HOST="localhost",
    )

    assert response.status_code == 200
    assert response.data["frontend_domain_status"] == Makerspace.DomainStatus.PENDING
    makerspace.refresh_from_db()
    assert makerspace.frontend_domain == "beta.example.com"
    assert makerspace.frontend_domain_status == Makerspace.DomainStatus.PENDING


@override_settings(PLATFORM_DOMAIN_SUFFIX="")
def test_selfhost_self_governed_space_manager_still_cannot_set_domain():
    # Strict superadmin-only: even a self-governed makerspace's Space Manager cannot
    # inject a process-global trusted staff origin (cross-tenant token-theft vector).
    makerspace = make_space("a2-selfgoverned")
    makerspace.superadmin_access_enabled = False
    makerspace.save(update_fields=["superadmin_access_enabled"])
    manager = make_member("a2-selfgoverned-manager", makerspace)

    response = authenticated_client(manager).patch(
        makerspace_detail_url(makerspace),
        {"frontend_domain": "governed.example.com"},
        format="json",
    )

    assert response.status_code == 400
    assert "frontend_domain" in response.data
    makerspace.refresh_from_db()
    assert makerspace.frontend_domain in (None, "")


# --- Part A / Task A2c: reconcile self-host domain trust across all write paths ----


@override_settings(PLATFORM_DOMAIN_SUFFIX="")
def test_selfhost_direct_create_with_domain_is_auto_verified():
    ms = Makerspace.objects.create(
        name="Direct", slug="a2c-direct", frontend_domain="direct.example.com"
    )
    ms.refresh_from_db()
    assert ms.frontend_domain_status == Makerspace.DomainStatus.VERIFIED
    assert ms.domain_verified_at is not None


@override_settings(PLATFORM_DOMAIN_SUFFIX="")
def test_selfhost_reconcile_promotes_preexisting_pending_row_on_save():
    ms = make_space("a2c-pending")
    # Simulate a row that carried a PENDING domain before the box went self-host,
    # writing it via .update() so the reconcile post_save signal does not fire yet.
    Makerspace.objects.filter(pk=ms.pk).update(
        frontend_domain="late.example.com",
        frontend_domain_status=Makerspace.DomainStatus.PENDING,
    )
    ms.refresh_from_db()
    assert ms.frontend_domain_status == Makerspace.DomainStatus.PENDING
    # Any ordinary save now reconciles it to VERIFIED.
    ms.location = "Lab 2"
    ms.save(update_fields=["location", "updated_at"])
    ms.refresh_from_db()
    assert ms.frontend_domain_status == Makerspace.DomainStatus.VERIFIED


@override_settings(PLATFORM_DOMAIN_SUFFIX="")
def test_selfhost_verified_domains_cache_reflects_create_and_clear(
    django_capture_on_commit_callbacks,
):
    from apps.makerspaces import hosting

    with django_capture_on_commit_callbacks(execute=True):
        ms = Makerspace.objects.create(
            name="Cache", slug="a2c-cache", frontend_domain="cache.example.com"
        )
    assert "cache.example.com" in hosting.verified_frontend_domains()

    # Clearing the domain must drop it from the trusted set (no stale trust).
    with django_capture_on_commit_callbacks(execute=True):
        ms.frontend_domain = None
        ms.save(update_fields=["frontend_domain", "updated_at"])
    assert "cache.example.com" not in hosting.verified_frontend_domains()


@override_settings(PLATFORM_DOMAIN_SUFFIX="")
def test_reconcile_command_promotes_selfhost_domains():
    from django.core.management import call_command

    ms = make_space("a2c-command")
    Makerspace.objects.filter(pk=ms.pk).update(
        frontend_domain="cmd.example.com",
        frontend_domain_status=Makerspace.DomainStatus.PENDING,
    )
    call_command("reconcile_selfhost_domains")
    ms.refresh_from_db()
    assert ms.frontend_domain_status == Makerspace.DomainStatus.VERIFIED


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me")
def test_reconcile_signal_dormant_on_managed(monkeypatch):
    # Managed mode: a pending custom domain must NOT be auto-promoted by the signal.
    monkeypatch.setattr(
        "apps.makerspaces.domain_verification._resolve_txt", lambda name: []
    )
    ms = make_space("a2c-managed-dormant")
    ms.frontend_domain = "managed.example.com"
    ms.save(update_fields=["frontend_domain", "updated_at"])
    ms.refresh_from_db()
    assert ms.frontend_domain_status != Makerspace.DomainStatus.VERIFIED


@override_settings(PLATFORM_DOMAIN_SUFFIX="")
def test_selfhost_update_rechecks_superadmin_gate_under_row_lock():
    # TOCTOU guard: validate() saw a no-op against the stale instance, but a concurrent
    # superadmin change means update() (under the lock) detects a real change — a
    # non-superadmin must still be rejected there, not silently write an auto-verified origin.
    from types import SimpleNamespace

    from rest_framework.serializers import ValidationError as DRFValidationError

    from apps.admin_api.serializers_makerspaces import MakerspaceSerializer

    makerspace = make_space("a2-toctou")
    Makerspace.objects.filter(pk=makerspace.pk).update(
        frontend_domain="orig.example.com",
        frontend_domain_status=Makerspace.DomainStatus.VERIFIED,
    )
    makerspace.refresh_from_db()
    manager = make_member("a2-toctou-manager", makerspace)

    serializer = MakerspaceSerializer(
        instance=makerspace,
        data={"frontend_domain": "orig.example.com"},  # looks like a no-op to validate()
        partial=True,
        context={"request": SimpleNamespace(user=manager)},
    )
    assert serializer.is_valid(), serializer.errors

    # A superadmin changes the domain between validate() and save()'s row lock.
    Makerspace.objects.filter(pk=makerspace.pk).update(
        frontend_domain="superadmin-set.example.com"
    )

    with pytest.raises(DRFValidationError):
        serializer.save()

    makerspace.refresh_from_db()
    assert makerspace.frontend_domain == "superadmin-set.example.com"  # not reverted
