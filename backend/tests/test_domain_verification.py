import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.makerspaces import domain_verification, platform
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


def test_verify_endpoint_handles_resolver_error_and_audits(monkeypatch):
    makerspace = set_domain(make_space("domain-resolver-error"))
    manager = make_member("domain-resolver-error-manager", makerspace)

    def fail_lookup(name):
        raise RuntimeError("resolver down")

    monkeypatch.setattr(domain_verification, "_resolve_txt", fail_lookup)

    response = authenticated_client(manager).post(verify_url(makerspace))

    makerspace.refresh_from_db()
    assert response.status_code == 200
    assert response.data["status"] == Makerspace.DomainStatus.FAILED
    assert response.data["token"] == makerspace.domain_verification_token
    assert response.data["expected_record"] == {
        "host": f"_osmm-verify.{makerspace.frontend_domain}",
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


def test_frontend_domain_change_resets_status_and_keeps_token_stable():
    makerspace = set_domain(make_space("domain-reset"), "old-reset.example")
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