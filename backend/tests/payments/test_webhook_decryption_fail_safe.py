import logging

import pytest
from cryptography.fernet import Fernet
from rest_framework.test import APIClient

from apps.payments.models import MakerspacePaymentSettings, PlatformStripeConnectSettings
from tests.return_helpers import make_space


pytestmark = pytest.mark.django_db
GENERIC_ERROR = {"detail": "Invalid Stripe webhook signature."}


def _connect_webhook(client):
    return client.post(
        "/api/v1/webhooks/stripe/connect",
        b"{}",
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE="invalid",
        HTTP_HOST="localhost",
    )


def test_connect_webhook_missing_encryption_key_returns_sanitized_400(
    settings, caplog
):
    settings.PLATFORM_DOMAIN_SUFFIX = ".managed.test"
    settings.API_CLIENT_ENC_KEY = Fernet.generate_key().decode()
    platform = PlatformStripeConnectSettings.load()
    platform.set_stripe_webhook_secret("whsec_must_not_leak")
    platform.save()
    ciphertext = platform.stripe_webhook_secret
    settings.API_CLIENT_ENC_KEY = ""

    with caplog.at_level(logging.WARNING):
        response = _connect_webhook(APIClient())

    assert response.status_code == 400
    assert response.data == GENERIC_ERROR
    assert "whsec_must_not_leak" not in caplog.text
    assert ciphertext not in caplog.text


def test_connect_webhook_corrupt_ciphertext_returns_sanitized_400(settings, caplog):
    settings.PLATFORM_DOMAIN_SUFFIX = ".managed.test"
    settings.API_CLIENT_ENC_KEY = Fernet.generate_key().decode()
    platform = PlatformStripeConnectSettings.load()
    corrupt = "fernet:corrupt-ciphertext-must-not-leak"
    PlatformStripeConnectSettings.objects.filter(pk=platform.pk).update(
        stripe_webhook_secret=corrupt
    )

    with caplog.at_level(logging.WARNING):
        response = _connect_webhook(APIClient())

    assert response.status_code == 400
    assert response.data == GENERIC_ERROR
    assert corrupt not in caplog.text


def test_raw_webhook_corrupt_ciphertext_returns_same_generic_400(settings):
    settings.API_CLIENT_ENC_KEY = Fernet.generate_key().decode()
    makerspace = make_space("raw-webhook-corrupt")
    payment_settings = MakerspacePaymentSettings.objects.create(
        makerspace=makerspace,
        stripe_secret_key="configured",
        stripe_webhook_secret="fernet:corrupt",
    )

    response = APIClient().post(
        f"/api/v1/webhooks/stripe/{makerspace.public_code}",
        b"{}",
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE="invalid",
    )

    assert response.status_code == 400
    assert response.data == GENERIC_ERROR
    assert payment_settings.stripe_webhook_secret not in str(response.data)


def test_self_host_connect_webhook_returns_404_before_decryption(settings, monkeypatch):
    settings.PLATFORM_DOMAIN_SUFFIX = ""
    decrypted = []
    monkeypatch.setattr(
        PlatformStripeConnectSettings,
        "get_stripe_webhook_secret",
        lambda _self: decrypted.append(True),
    )

    response = _connect_webhook(APIClient())

    assert response.status_code == 404
    assert decrypted == []
