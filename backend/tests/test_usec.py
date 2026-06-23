import pytest
from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.hardware_requests.models import HardwareRequest
from apps.inventory.models import InventoryProduct
from apps.makerspaces.models import Makerspace

pytestmark = pytest.mark.django_db


def make_space(slug="usec-lab"):
    return Makerspace.objects.create(name=slug, slug=slug)


def make_product(makerspace):
    return InventoryProduct.objects.create(
        makerspace=makerspace,
        name="Logic Analyzer",
        description="Bench diagnostics",
        total_quantity=5,
        available_quantity=5,
        reserved_quantity=0,
        is_public=True,
        is_archived=False,
    )


def submit_url(makerspace):
    return f"/api/v1/public/{makerspace.slug}/requests"


def submit_payload(product, **overrides):
    payload = {
        "requester_name": "Checked In User",
        "contact_email": "checked-in-user@example.com",
        "contact_phone": "+15550101010",
        "requested_for": "Bench diagnostics",
        "items": [{"product_id": product.id, "quantity": 1}],
    }
    payload.update(overrides)
    return payload


@override_settings(API_CLIENT_AUTH_REQUIRED=False, CHECKIN_MODE="stub")
def test_public_submit_honeypot_returns_success_without_creating_request():
    makerspace = make_space("usec-honeypot")
    product = make_product(makerspace)
    client = APIClient()

    spam = client.post(
        submit_url(makerspace),
        submit_payload(product, website="https://spam.example"),
        format="json",
    )

    assert spam.status_code == 201
    assert set(spam.data) == {"public_token", "status"}
    assert spam.data["status"] == HardwareRequest.Status.PENDING_APPROVAL
    assert HardwareRequest.objects.count() == 0

    # Honeypot filled AND a required field garbled must STILL fake-success (201), not
    # leak a 400 validation error that would reveal the honeypot as the trigger.
    malformed = client.post(
        submit_url(makerspace),
        {"website": "https://spam.example", "items": []},
        format="json",
    )
    assert malformed.status_code == 201
    assert HardwareRequest.objects.count() == 0

    clean = client.post(submit_url(makerspace), submit_payload(product), format="json")

    assert clean.status_code == 201
    assert set(clean.data) == {"public_token", "status"}
    assert HardwareRequest.objects.count() == 1
    assert str(HardwareRequest.objects.get().public_token) == clean.data["public_token"]


@override_settings(AXES_ENABLED=True, AXES_FAILURE_LIMIT=2)
def test_repeated_failed_admin_logins_are_locked_out():
    from axes.utils import reset

    user_model = get_user_model()
    user_model.objects.create_superuser(
        username="admin-lock",
        email="admin-lock@example.com",
        password="pw-strong-123",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )
    client = Client()

    try:
        responses = [
            client.post(
                "/control/login/",
                {"username": "admin-lock", "password": "wrong", "next": "/control/"},
            )
            for _ in range(3)
        ]

        assert responses[-1].status_code == django_settings.AXES_HTTP_RESPONSE_CODE
    finally:
        reset()


@override_settings(AXES_ENABLED=True)
def test_jwt_login_succeeds_when_axes_is_enabled():
    get_user_model().objects.create_user(
        username="jwt-usec",
        email="jwt-usec@example.com",
        password="pw-strong-123",
        role=User.Role.SPACE_MANAGER,
        access_status=User.AccessStatus.ACTIVE,
    )

    response = APIClient().post(
        "/api/v1/auth/login",
        {"username": "jwt-usec", "password": "pw-strong-123"},
        format="json",
    )

    assert response.status_code == 200
    assert "access" in response.data


def test_tls_hardening_defaults_off_for_http_docker_deployment():
    """Regression: the default Docker/prod stack serves plain HTTP behind nginx.
    SSL redirect and Secure cookies must default OFF (env-gated, not DEBUG-gated)
    or the healthcheck/API/admin-login break. Operators set ENABLE_HTTPS=true with TLS."""
    from django.conf import settings

    assert settings.SECURE_SSL_REDIRECT is False
    assert settings.SESSION_COOKIE_SECURE is False
    assert settings.CSRF_COOKIE_SECURE is False
    assert settings.SECURE_HSTS_SECONDS == 0
    # Transport-independent headers stay on regardless.
    assert settings.SECURE_CONTENT_TYPE_NOSNIFF is True
    assert settings.X_FRAME_OPTIONS == "DENY"
