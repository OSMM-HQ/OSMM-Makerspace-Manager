from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.admin_api.serializers_makerspaces import MakerspaceSerializer
from apps.makerspaces import domain_verification
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
    assert provisioned.frontend_domain_changed_at is not None


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


@override_settings(PLATFORM_DOMAIN_SUFFIX='.osmm.me', INFRA_HOSTS={'testserver'})
@pytest.mark.django_db
def test_tls_check_allows_verified_custom_domain():
    makerspace = make_space('tls-verified-custom')
    makerspace.frontend_domain = 'tools.acme.com'
    makerspace.frontend_domain_status = Makerspace.DomainStatus.VERIFIED
    makerspace.save()
    from apps.makerspaces import hosting

    hosting.invalidate()
    response = APIClient().get(
        '/api/v1/internal/tls-check',
        {'domain': 'tools.acme.com'},
        HTTP_HOST='testserver',
    )

    assert response.status_code == 200


@override_settings(PLATFORM_DOMAIN_SUFFIX='.osmm.me', INFRA_HOSTS={'testserver'})
@pytest.mark.django_db
def test_tls_check_denies_pending_domain():
    makerspace = make_space('tls-pending-custom')
    makerspace.frontend_domain = 'pending.acme.com'
    makerspace.frontend_domain_status = Makerspace.DomainStatus.PENDING
    makerspace.save()
    from apps.makerspaces import hosting

    hosting.invalidate()
    response = APIClient().get(
        '/api/v1/internal/tls-check',
        {'domain': 'pending.acme.com'},
        HTTP_HOST='testserver',
    )

    assert response.status_code == 403


@override_settings(PLATFORM_DOMAIN_SUFFIX='.osmm.me', INFRA_HOSTS={'testserver'})
@pytest.mark.django_db
def test_tls_check_denies_verified_platform_domain():
    makerspace = make_space('tls-platform-domain')
    makerspace.frontend_domain = 'acme.osmm.me'
    makerspace.frontend_domain_status = Makerspace.DomainStatus.VERIFIED
    makerspace.save()
    from apps.makerspaces import hosting

    hosting.invalidate()
    response = APIClient().get(
        '/api/v1/internal/tls-check',
        {'domain': 'acme.osmm.me'},
        HTTP_HOST='testserver',
    )

    assert response.status_code == 403


@override_settings(PLATFORM_DOMAIN_SUFFIX='.osmm.me', INFRA_HOSTS={'testserver'})
@pytest.mark.django_db
@pytest.mark.parametrize(
    'domain',
    ['203.0.113.5', 'acme.osmm.me:443', None, ''],
)
def test_tls_check_denies_invalid_or_missing_domain(domain):
    params = {} if domain is None else {'domain': domain}

    response = APIClient().get(
        '/api/v1/internal/tls-check',
        params,
        HTTP_HOST='testserver',
    )

    assert response.status_code == 403


@override_settings(PLATFORM_DOMAIN_SUFFIX='.osmm.me', INFRA_HOSTS={'testserver'})
@pytest.mark.django_db
def test_tls_check_fails_closed_when_verified_domain_lookup_errors(monkeypatch):
    monkeypatch.setattr(
        'apps.makerspaces.hosting.verified_frontend_domains',
        lambda: (_ for _ in ()).throw(RuntimeError('db down')),
    )

    response = APIClient().get(
        '/api/v1/internal/tls-check',
        {'domain': 'tools.acme.com'},
        HTTP_HOST='testserver',
    )
    ordinary_denial = APIClient().get(
        '/api/v1/internal/tls-check',
        HTTP_HOST='testserver',
    )

    assert response.status_code == 403
    assert (response.status_code, response.content) == (
        ordinary_denial.status_code,
        ordinary_denial.content,
    )


@override_settings(PLATFORM_DOMAIN_SUFFIX='.osmm.me', INFRA_HOSTS={'testserver'})
@pytest.mark.django_db
def test_tls_check_denials_are_non_enumerable():
    pending = make_space('tls-denial-pending')
    pending.frontend_domain = 'pending.example.com'
    pending.frontend_domain_status = Makerspace.DomainStatus.PENDING
    pending.save()
    platform = make_space('tls-denial-platform')
    platform.frontend_domain = 'platform.osmm.me'
    platform.frontend_domain_status = Makerspace.DomainStatus.VERIFIED
    platform.save()
    from apps.makerspaces import hosting

    hosting.invalidate()
    client = APIClient()
    responses = [
        client.get(
            '/api/v1/internal/tls-check',
            params,
            HTTP_HOST='testserver',
        )
        for params in (
            {'domain': 'pending.example.com'},
            {'domain': 'platform.osmm.me'},
            {'domain': 'unknown.example.com'},
            {'domain': '203.0.113.5'},
            {'domain': 'platform.osmm.me:443'},
            {},
            {'domain': ''},
        )
    ]

    assert {(response.status_code, response.content) for response in responses} == {
        (403, responses[0].content)
    }


@override_settings(PLATFORM_DOMAIN_SUFFIX='.osmm.me', PLATFORM_ORIGIN_HOST='origin.osmm.me')
@pytest.mark.django_db
def test_verify_domain_fails_when_txt_matches_but_origin_does_not(monkeypatch):
    makerspace = make_space('origin-gate-failed')
    makerspace.frontend_domain = 'tools.acme.com'
    makerspace.save()
    monkeypatch.setattr(
        domain_verification,
        '_resolve_txt',
        lambda name: [makerspace.domain_verification_token],
    )
    monkeypatch.setattr(domain_verification, 'resolves_to_origin', lambda instance: False)

    status, verified_at, detail = domain_verification.verify_domain(makerspace)

    assert status == Makerspace.DomainStatus.FAILED
    assert verified_at is None
    assert detail == 'Domain does not resolve to the platform origin yet.'
    makerspace.refresh_from_db()
    assert makerspace.frontend_domain_status == Makerspace.DomainStatus.FAILED


@override_settings(PLATFORM_DOMAIN_SUFFIX='.osmm.me', PLATFORM_ORIGIN_HOST='origin.osmm.me')
@pytest.mark.django_db
def test_verify_domain_succeeds_when_txt_and_origin_match(monkeypatch):
    makerspace = make_space('origin-gate-verified')
    makerspace.frontend_domain = 'tools.acme.com'
    makerspace.save()
    monkeypatch.setattr(
        domain_verification,
        '_resolve_txt',
        lambda name: [makerspace.domain_verification_token],
    )
    monkeypatch.setattr(domain_verification, 'resolves_to_origin', lambda instance: True)

    status, verified_at, detail = domain_verification.verify_domain(makerspace)

    assert status == Makerspace.DomainStatus.VERIFIED
    assert verified_at is not None
    assert detail == 'Domain verified.'


@override_settings(PLATFORM_DOMAIN_SUFFIX='.osmm.me', PLATFORM_ORIGIN_HOST='')
@pytest.mark.django_db
def test_verify_domain_keeps_legacy_txt_only_behavior_when_origin_is_blank(monkeypatch):
    makerspace = make_space('origin-gate-dormant')
    makerspace.frontend_domain = 'tools.acme.com'
    makerspace.save()
    monkeypatch.setattr(
        domain_verification,
        '_resolve_txt',
        lambda name: [makerspace.domain_verification_token],
    )

    status, verified_at, detail = domain_verification.verify_domain(makerspace)

    assert status == Makerspace.DomainStatus.VERIFIED
    assert verified_at is not None
    assert detail == 'Domain verified.'


@override_settings(
    PLATFORM_DOMAIN_SUFFIX='.osmm.me',
    INFRA_HOSTS={'testserver'},
    DOMAIN_CHANGE_COOLDOWN_SECONDS=3600,
)
@pytest.mark.django_db
def test_domain_change_cooldown_rejects_a_second_change():
    makerspace = make_space('domain-cooldown-rejected')
    manager = make_member('domain-cooldown-rejected-manager', makerspace)
    client = authenticated_client(manager)
    url = f'/api/v1/admin/makerspaces/{makerspace.id}'

    first = client.patch(
        url,
        {'frontend_domain': 'first.example.com'},
        format='json',
        HTTP_HOST='testserver',
    )
    makerspace.refresh_from_db()
    second = client.patch(
        url,
        {'frontend_domain': 'second.example.com'},
        format='json',
        HTTP_HOST='testserver',
    )

    assert first.status_code == 200
    assert makerspace.frontend_domain_changed_at is not None
    assert second.status_code == 400
    assert second.data['frontend_domain'] == [
        'You changed your domain recently; please wait before changing it again.'
    ]


@override_settings(
    PLATFORM_DOMAIN_SUFFIX='.osmm.me',
    INFRA_HOSTS={'testserver'},
    DOMAIN_CHANGE_COOLDOWN_SECONDS=3600,
)
@pytest.mark.django_db
def test_domain_change_is_allowed_after_cooldown_passes():
    makerspace = make_space('domain-cooldown-expired')
    makerspace.frontend_domain = 'old.example.com'
    makerspace.frontend_domain_changed_at = timezone.now() - timedelta(hours=2)
    makerspace.save()
    manager = make_member('domain-cooldown-expired-manager', makerspace)

    response = authenticated_client(manager).patch(
        f'/api/v1/admin/makerspaces/{makerspace.id}',
        {'frontend_domain': 'new.example.com'},
        format='json',
        HTTP_HOST='testserver',
    )

    assert response.status_code == 200
    makerspace.refresh_from_db()
    assert makerspace.frontend_domain == 'new.example.com'
    assert makerspace.frontend_domain_changed_at > timezone.now() - timedelta(minutes=1)


@override_settings(
    PLATFORM_DOMAIN_SUFFIX='.osmm.me',
    INFRA_HOSTS={'testserver'},
    DOMAIN_CHANGE_COOLDOWN_SECONDS=0,
)
@pytest.mark.django_db
def test_domain_change_cooldown_is_dormant_when_zero():
    makerspace = make_space('domain-cooldown-dormant')
    makerspace.frontend_domain = 'old-zero.example.com'
    makerspace.frontend_domain_changed_at = timezone.now()
    makerspace.save()
    manager = make_member('domain-cooldown-dormant-manager', makerspace)

    response = authenticated_client(manager).patch(
        f'/api/v1/admin/makerspaces/{makerspace.id}',
        {'frontend_domain': 'new-zero.example.com'},
        format='json',
        HTTP_HOST='testserver',
    )

    assert response.status_code == 200


# --- Stage-4 review fixes -----------------------------------------------------


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me")
@pytest.mark.django_db
def test_serializer_rejects_platform_apex():
    space = make_space("apex-reject")
    serializer = MakerspaceSerializer(
        instance=space, data={"frontend_domain": "osmm.me"}, partial=True
    )
    assert not serializer.is_valid()
    assert "frontend_domain" in serializer.errors


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me")
@pytest.mark.django_db
def test_serializer_rejects_platform_subdomain_claim():
    space = make_space("sub-reject")
    serializer = MakerspaceSerializer(
        instance=space, data={"frontend_domain": "acme.osmm.me"}, partial=True
    )
    assert not serializer.is_valid()
    assert "frontend_domain" in serializer.errors


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me")
@pytest.mark.django_db
def test_serializer_allows_noop_platform_domain_update():
    space = make_space("noop-update")
    space.frontend_domain = "acme.osmm.me"
    space.frontend_domain_status = Makerspace.DomainStatus.VERIFIED
    space.save()
    serializer = MakerspaceSerializer(
        instance=space,
        data={"frontend_domain": "acme.osmm.me", "hidden_from_central_directory": True},
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me")
@pytest.mark.django_db
def test_verify_domain_platform_subdomain_stays_verified(monkeypatch):
    space = make_space("plat-verify")
    space.frontend_domain = "acme.osmm.me"
    space.frontend_domain_status = Makerspace.DomainStatus.PENDING
    space.save()

    def _no_dns(name):
        raise AssertionError("platform subdomains must not trigger a DNS lookup")

    monkeypatch.setattr(domain_verification, "_resolve_txt", _no_dns)
    status, _verified_at, _detail = domain_verification.verify_domain(space)
    assert status == Makerspace.DomainStatus.VERIFIED
    space.refresh_from_db()
    assert space.frontend_domain_status == Makerspace.DomainStatus.VERIFIED


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me", PLATFORM_ORIGIN_HOST="")
@pytest.mark.django_db
def test_verify_domain_aborts_on_concurrent_domain_change(monkeypatch):
    # DB row holds domain B; a stale in-memory instance still points at domain A.
    space = make_space("race")
    space.frontend_domain = "b.example.com"
    space.frontend_domain_status = Makerspace.DomainStatus.PENDING
    space.save()

    stale = Makerspace.objects.get(pk=space.pk)
    stale.frontend_domain = "a.example.com"  # in memory only — never saved
    monkeypatch.setattr(
        domain_verification, "_resolve_txt", lambda name: [stale.domain_verification_token]
    )

    _status, _verified_at, detail = domain_verification.verify_domain(stale)
    assert "changed during verification" in detail
    space.refresh_from_db()
    # Domain B must NOT have been granted VERIFIED off the stale A verification.
    assert space.frontend_domain_status == Makerspace.DomainStatus.PENDING
