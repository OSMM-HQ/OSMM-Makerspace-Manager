import pytest
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from apps.accounts.models import User
from apps.makerspaces.hosting import (
    canonical_host,
    host_is_allowed,
    verified_frontend_domains,
)
from apps.makerspaces.middleware import TenantHostValidationMiddleware
from apps.makerspaces.models import Makerspace
from apps.makerspaces.provisioning import provision_subdomain
from tests.return_helpers import authenticated_client, make_member, make_space, make_user


def test_canonical_host_normalizes_and_rejects():
    assert canonical_host("ACME.osmm.me:443") == "acme.osmm.me"
    assert canonical_host("acme.osmm.me.") == "acme.osmm.me"
    assert canonical_host("203.0.113.5") is None
    assert canonical_host("bad_host!") is None


@pytest.mark.django_db
def test_verified_domains_only_includes_verified(settings):
    settings.PLATFORM_DOMAIN_SUFFIX = ".osmm.me"
    m = Makerspace.objects.create(name="Acme", slug="acme")
    m.frontend_domain = "tools.acme.com"
    m.frontend_domain_status = Makerspace.DomainStatus.PENDING
    m.save()
    from apps.makerspaces import hosting

    hosting.invalidate()
    assert "tools.acme.com" not in verified_frontend_domains()
    m.frontend_domain_status = Makerspace.DomainStatus.VERIFIED
    m.save()
    hosting.invalidate()
    assert "tools.acme.com" in verified_frontend_domains()


@pytest.mark.django_db
def test_host_is_allowed_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "apps.makerspaces.hosting.verified_frontend_domains",
        lambda: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    assert host_is_allowed("tools.acme.com") is False


@pytest.mark.django_db
def test_host_validation_middleware_rejects_unknown_and_passes_infra(settings):
    settings.PLATFORM_DOMAIN_SUFFIX = ".osmm.me"
    settings.INFRA_HOSTS = {"backend", "backend:8000"}
    middleware = TenantHostValidationMiddleware(lambda request: HttpResponse("ok"))
    factory = RequestFactory()

    rejected = middleware(factory.get("/known-view", HTTP_HOST="unknown.example"))
    allowed = middleware(factory.get("/known-view", HTTP_HOST="backend:8000"))

    assert rejected.status_code == 400
    assert allowed.status_code == 200
    assert allowed.content == b"ok"


def test_host_validation_middleware_is_passthrough_when_suffix_blank(settings):
    settings.PLATFORM_DOMAIN_SUFFIX = ""
    middleware = TenantHostValidationMiddleware(lambda request: HttpResponse("unchanged"))

    response = middleware(RequestFactory().get("/known-view", HTTP_HOST="unknown.example"))

    assert response.status_code == 200
    assert response.content == b"unchanged"


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me", INFRA_HOSTS={"testserver"})
@pytest.mark.django_db
def test_tenant_makerspace_update_rejects_platform_subdomain():
    makerspace = make_space("tenant-domain-guard")
    manager = make_member("tenant-domain-guard-manager", makerspace)
    response = authenticated_client(manager).patch(
        f"/api/v1/admin/makerspaces/{makerspace.id}",
        {"frontend_domain": "X.OSMM.ME"},
        format="json",
        HTTP_HOST="testserver",
    )

    assert response.status_code == 400
    assert response.data["frontend_domain"] == [
        "Platform subdomains are provisioned by staff, not set directly."
    ]
    makerspace.refresh_from_db()
    assert makerspace.frontend_domain is None


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me")
@pytest.mark.django_db
def test_provision_subdomain_sets_verified_platform_domain():
    makerspace = make_space("provision-acme")
    superadmin = make_user(
        "provision-acme-superadmin",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
        is_staff=True,
        is_superuser=True,
    )

    provisioned = provision_subdomain(makerspace, " AcMe ", superadmin)

    assert provisioned.frontend_domain == "acme.osmm.me"
    assert provisioned.frontend_domain_status == Makerspace.DomainStatus.VERIFIED
    assert provisioned.domain_verified_at is not None


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me")
@pytest.mark.django_db
def test_provision_subdomain_rejects_reserved_label():
    makerspace = make_space("provision-reserved")
    superadmin = make_user(
        "provision-reserved-superadmin",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )

    with pytest.raises(ValidationError):
        provision_subdomain(makerspace, "api", superadmin)


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me")
@pytest.mark.django_db
def test_provision_subdomain_rejects_multi_label():
    makerspace = make_space("provision-multi-label")
    superadmin = make_user(
        "provision-multi-label-superadmin",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )

    with pytest.raises(ValidationError):
        provision_subdomain(makerspace, "a.b", superadmin)


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me")
@pytest.mark.django_db
def test_provision_subdomain_rejects_case_insensitive_collision():
    first = make_space("provision-duplicate-first")
    second = make_space("provision-duplicate-second")
    superadmin = make_user(
        "provision-duplicate-superadmin",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )
    provision_subdomain(first, "DuP", superadmin)

    with pytest.raises(ValidationError):
        provision_subdomain(second, "dup", superadmin)


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me", INFRA_HOSTS={"testserver"})
@pytest.mark.django_db
def test_provision_subdomain_endpoint_requires_superadmin():
    makerspace = make_space("provision-endpoint")
    manager = make_member("provision-endpoint-manager", makerspace)
    url = f"/api/v1/admin/makerspace/{makerspace.id}/provision-subdomain"

    denied = authenticated_client(manager).post(
        url, {"label": "endpoint"}, format="json", HTTP_HOST="testserver"
    )

    assert denied.status_code == 403

    superadmin = make_user(
        "provision-endpoint-superadmin",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
        is_staff=True,
        is_superuser=True,
    )
    allowed = authenticated_client(superadmin).post(
        url,
        {"label": "endpoint"},
        format="json",
        HTTP_HOST="testserver",
    )

    assert allowed.status_code == 200
    assert allowed.data["frontend_domain"] == "endpoint.osmm.me"
    assert allowed.data["frontend_domain_status"] == Makerspace.DomainStatus.VERIFIED
