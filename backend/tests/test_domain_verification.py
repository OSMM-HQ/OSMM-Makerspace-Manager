import pytest
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.makerspaces import domain_verification, middleware, platform
from apps.makerspaces.models import Makerspace, MakerspaceMembership
from tests.return_helpers import authenticated_client, make_member, make_space, make_user

pytestmark = pytest.mark.django_db


def verify_url(makerspace):
    return reverse("makerspace-verify-domain", kwargs={"makerspace_id": makerspace.id})


def set_domain(makerspace, domain="verify.example"):
    makerspace.frontend_domain = domain
    makerspace.save(update_fields=["frontend_domain"])
    makerspace.refresh_from_db()
    return makerspace


@override_settings(PLATFORM_DOMAIN_SUFFIX=".space-works.tech")
def test_verify_domain_marks_verified_when_token_present(monkeypatch):
    makerspace = set_domain(make_space("domain-verified"))
    monkeypatch.setattr(
        domain_verification,
        "_resolve_txt",
        lambda name: ["other-token", makerspace.domain_verification_token],
    )

    status, verified_at, detail = domain_verification.verify_domain(makerspace)

    makerspace.refresh_from_db()
    assert status == Makerspace.DomainStatus.VERIFIED
    assert makerspace.frontend_domain_status == Makerspace.DomainStatus.VERIFIED
    assert makerspace.domain_verified_at is not None
    assert verified_at == makerspace.domain_verified_at
    assert detail == "Domain verified."

@override_settings(PLATFORM_DOMAIN_SUFFIX=".space-works.tech")
def test_verify_domain_accepts_legacy_osmm_txt_label(monkeypatch):
    makerspace = set_domain(make_space("legacy-domain-verified"))

    def resolve_txt(name):
        if name.startswith("_osmm-verify."):
            return [makerspace.domain_verification_token]
        return []

    monkeypatch.setattr(domain_verification, "_resolve_txt", resolve_txt)

    status, _, detail = domain_verification.verify_domain(makerspace)

    assert status == Makerspace.DomainStatus.VERIFIED
    assert detail == "Domain verified."

@override_settings(PLATFORM_DOMAIN_SUFFIX=".space-works.tech")
def test_verify_domain_marks_failed_when_token_absent(monkeypatch):
    makerspace = set_domain(make_space("domain-token-absent"))
    old_verified_at = timezone.now()
    makerspace.frontend_domain_status = Makerspace.DomainStatus.VERIFIED
    makerspace.domain_verified_at = old_verified_at
    makerspace.save(update_fields=["frontend_domain_status", "domain_verified_at"])
    monkeypatch.setattr(domain_verification, "_resolve_txt", lambda name: ["wrong-token"])

    status, verified_at, detail = domain_verification.verify_domain(makerspace)

    makerspace.refresh_from_db()
    assert status == Makerspace.DomainStatus.FAILED
    assert makerspace.frontend_domain_status == Makerspace.DomainStatus.FAILED
    assert makerspace.domain_verified_at == old_verified_at
    assert verified_at == old_verified_at
    assert "not found" in detail


@override_settings(PLATFORM_DOMAIN_SUFFIX=".space-works.tech")
def test_verify_endpoint_handles_resolver_error_and_audits(monkeypatch):
    makerspace = set_domain(make_space("domain-resolver-error"))
    manager = make_member("domain-resolver-error-manager", makerspace)

    def fail_lookup(name):
        raise RuntimeError("resolver down")

    monkeypatch.setattr(domain_verification, "_resolve_txt", fail_lookup)

    # Managed mode activates TenantHostValidationMiddleware, which reads HTTP_HOST;
    # use an infra host so the request reaches the view (Caddy sets this in prod).
    response = authenticated_client(manager).post(verify_url(makerspace), HTTP_HOST="localhost")

    makerspace.refresh_from_db()
    assert response.status_code == 200
    assert response.data["status"] == Makerspace.DomainStatus.FAILED
    assert response.data["token"] == makerspace.domain_verification_token
    assert response.data["expected_record"] == {
        "host": f"_spaceworks-verify.{makerspace.frontend_domain}",
        "type": "TXT",
        "value": makerspace.domain_verification_token,
    }
    assert "DNS lookup failed" in response.data["detail"]
    assert makerspace.frontend_domain_status == Makerspace.DomainStatus.FAILED
    audit = AuditLog.objects.get(action="makerspace.domain_verify_attempt")
    assert audit.makerspace == makerspace
    assert audit.meta == {"domain": makerspace.frontend_domain, "status": "failed"}


def test_verify_endpoint_manage_makerspace_gating():
    own_space = set_domain(make_space("domain-rbac-own"), "own-rbac.example")
    other_space = set_domain(make_space("domain-rbac-other"), "other-rbac.example")
    archived = set_domain(make_space("domain-rbac-archived"), "archived-rbac.example")
    hidden = set_domain(make_space("domain-rbac-hidden"), "hidden-rbac.example")
    archived.archived_at = timezone.now()
    archived.save(update_fields=["archived_at"])
    hidden.superadmin_access_enabled = False
    hidden.save(update_fields=["superadmin_access_enabled"])
    inventory_manager = make_member(
        "domain-rbac-inventory",
        own_space,
        membership_role=MakerspaceMembership.Role.INVENTORY_MANAGER,
    )
    manager = make_member("domain-rbac-manager", own_space)
    superadmin = make_user(
        "domain-rbac-superadmin",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
        is_staff=True,
        is_superuser=True,
    )

    assert authenticated_client(inventory_manager).post(verify_url(own_space)).status_code == 403
    assert authenticated_client(manager).post(verify_url(other_space)).status_code == 404
    assert authenticated_client(superadmin).post(verify_url(archived)).status_code == 404
    assert authenticated_client(superadmin).post(verify_url(hidden)).status_code == 404


@override_settings(PLATFORM_DOMAIN_SUFFIX=".space-works.tech")
def test_frontend_domain_change_resets_status_and_keeps_token_stable():
    # Managed mode: changing a custom domain re-enters the TXT flow => PENDING.
    makerspace = set_domain(make_space("domain-reset"), "old-reset.example")
    makerspace.resource_limit_overrides = {"custom_domain": True}
    makerspace.save(update_fields=["resource_limit_overrides"])
    old_token = makerspace.domain_verification_token
    makerspace.frontend_domain_status = Makerspace.DomainStatus.VERIFIED
    makerspace.domain_verified_at = timezone.now()
    makerspace.save(update_fields=["frontend_domain_status", "domain_verified_at"])
    manager = make_member("domain-reset-manager", makerspace)

    response = authenticated_client(manager).patch(
        reverse("admin-makerspace", kwargs={"pk": makerspace.id}),
        {
            "frontend_domain": "new-reset.example",
            "frontend_domain_status": "verified",
            "domain_verification_token": "client-forged-token",
        },
        format="json",
        HTTP_HOST="localhost",
    )

    makerspace.refresh_from_db()
    assert response.status_code == 200
    assert makerspace.frontend_domain == "new-reset.example"
    assert makerspace.frontend_domain_status == Makerspace.DomainStatus.PENDING
    assert makerspace.domain_verified_at is None
    assert makerspace.domain_verification_token == old_token


def test_clearing_frontend_domain_resets_status_and_record():
    makerspace = set_domain(make_space("domain-clear"), "clear-reset.example")
    makerspace.frontend_domain_status = Makerspace.DomainStatus.VERIFIED
    makerspace.domain_verified_at = timezone.now()
    makerspace.hidden_from_central_directory = True
    makerspace.save(
        update_fields=[
            "frontend_domain_status",
            "domain_verified_at",
            "hidden_from_central_directory",
        ]
    )
    manager = make_member("domain-clear-manager", makerspace)

    response = authenticated_client(manager).patch(
        reverse("admin-makerspace", kwargs={"pk": makerspace.id}),
        {"frontend_domain": ""},
        format="json",
    )

    makerspace.refresh_from_db()
    assert response.status_code == 200
    assert makerspace.frontend_domain is None
    assert makerspace.frontend_domain_status == Makerspace.DomainStatus.PENDING
    assert makerspace.domain_verified_at is None
    assert response.data["domain_verification_record"] is None


def test_resolve_frontend_and_bootstrap_do_not_touch_dns(monkeypatch):
    makerspace = set_domain(make_space("domain-hot-path"), "hot-path.example")

    def fail_if_called(name):
        raise AssertionError("DNS should not run outside explicit verification")

    monkeypatch.setattr(domain_verification, "_resolve_txt", fail_if_called)

    assert platform.resolve_frontend(host="hot-path.example") == makerspace
    response = APIClient().get("/api/v1/bootstrap", HTTP_ORIGIN="https://hot-path.example")
    assert response.status_code == 200
    assert response.data["makerspace"]["slug"] == makerspace.slug

# --- Part A: self-host custom-domain auto-trust ---------------------------------


@override_settings(PLATFORM_DOMAIN_SUFFIX="")
def test_selfhost_domain_is_trusted_without_txt():
    ms = Makerspace.objects.create(
        name="Alpha SH", slug="selfhost-trust-alpha", frontend_domain="alpha.example.com"
    )
    status, verified_at, detail = domain_verification.verify_domain(ms)
    assert status == Makerspace.DomainStatus.VERIFIED
    assert verified_at is not None
    assert "trusted automatically" in detail.lower()
    assert domain_verification.expected_record(ms) is None
    ms.refresh_from_db()
    assert ms.frontend_domain_status == Makerspace.DomainStatus.VERIFIED
    assert ms.domain_verified_at is not None


@override_settings(PLATFORM_DOMAIN_SUFFIX=".space-works.tech")
def test_managed_custom_domain_without_txt_fails(monkeypatch):
    # Managed path unchanged: a non-platform domain with no TXT record => FAILED.
    monkeypatch.setattr(domain_verification, "_resolve_txt", lambda name: [])
    ms = Makerspace.objects.create(
        name="Beta MG", slug="managed-fail-beta", frontend_domain="beta.example.com"
    )
    status, _verified_at, _detail = domain_verification.verify_domain(ms)
    assert status == Makerspace.DomainStatus.FAILED
    assert domain_verification.expected_record(ms) is not None


@override_settings(PLATFORM_DOMAIN_SUFFIX="   ")
def test_whitespace_suffix_is_treated_as_self_host():
    assert domain_verification.is_self_host() is True


@override_settings(PLATFORM_DOMAIN_SUFFIX="   ")
def test_middleware_passes_through_on_whitespace_suffix():
    called = {"n": 0}

    def get_response(request):
        called["n"] += 1
        return "ok"

    mw = middleware.TenantHostValidationMiddleware(get_response)
    request = RequestFactory().get("/", HTTP_HOST="not-a-real-allowed-host.invalid")
    assert mw(request) == "ok"
    assert called["n"] == 1


def test_platform_suffix_normalization_prepends_leading_dot():
    from config.settings import normalize_platform_domain_suffix

    assert normalize_platform_domain_suffix("space-works.tech") == ".space-works.tech"
    assert normalize_platform_domain_suffix(".space-works.tech") == ".space-works.tech"
    assert normalize_platform_domain_suffix("space-works.tech") == ".space-works.tech"
    assert normalize_platform_domain_suffix("  ") == ""
    assert normalize_platform_domain_suffix("") == ""
    assert normalize_platform_domain_suffix(None) == ""
