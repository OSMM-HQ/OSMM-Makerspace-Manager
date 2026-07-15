import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from apps.makerspaces.hosting import (
    canonical_host,
    host_is_allowed,
    verified_frontend_domains,
)
from apps.makerspaces.middleware import TenantHostValidationMiddleware
from apps.makerspaces.models import Makerspace


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
