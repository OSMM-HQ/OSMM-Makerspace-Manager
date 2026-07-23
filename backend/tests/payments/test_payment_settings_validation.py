from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from django.contrib import admin
from rest_framework.test import APIClient

from apps.payments.models import MakerspacePaymentSettings, Payment
from tests.payments.test_machine_payments import service_request
from tests.return_helpers import make_member, make_space


pytestmark = pytest.mark.django_db


def pending_raw_settings(slug):
    makerspace = make_space(slug)
    manager = make_member(f"{slug}-manager", makerspace)
    payment_settings = MakerspacePaymentSettings(makerspace=makerspace)
    payment_settings.set_stripe_secret_key("sk_raw")
    payment_settings.set_stripe_webhook_secret("whsec_raw")
    payment_settings.save()
    subject = service_request(makerspace, manager)
    payment = Payment.objects.create(
        makerspace=makerspace,
        subject_type=Payment.SubjectType.MACHINE_SERVICE_REQUEST,
        subject_id=subject.id,
        member=manager,
        amount=Decimal("2.00"),
        currency="usd",
        created_by=manager,
        stripe_provider=Payment.StripeProvider.RAW,
    )
    Payment.objects.filter(pk=payment.pk).update(
        stripe_checkout_session_id=f"cs_{slug}"
    )
    return makerspace, manager, payment_settings


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stripe_secret_key", "sk_raw_rotated"),
        ("stripe_secret_key", ""),
        ("stripe_webhook_secret", "whsec_raw_rotated"),
        ("stripe_webhook_secret", ""),
    ],
)
def test_api_blocks_raw_credential_mutation_while_session_is_pending(field, value):
    makerspace, manager, payment_settings = pending_raw_settings(
        f"payment-rotation-{field.removeprefix('stripe_')[:7]}-{bool(value)}"
    )
    client = APIClient()
    client.force_authenticate(manager)

    response = client.patch(
        f"/api/v1/admin/makerspace/{makerspace.id}/payment-settings",
        {field: value},
        format="json",
    )

    assert response.status_code == 400
    assert "pending" in str(response.data[field]).lower()
    payment_settings.refresh_from_db()
    assert payment_settings.get_stripe_secret_key() == "sk_raw"
    assert payment_settings.get_stripe_webhook_secret() == "whsec_raw"


def unreadable_raw_settings(settings, slug, unreadable, *, pending):
    settings.API_CLIENT_ENC_KEY = Fernet.generate_key().decode()
    if pending:
        makerspace, manager, payment_settings = pending_raw_settings(slug)
    else:
        makerspace = make_space(slug)
        manager = make_member(f"{slug}-manager", makerspace)
        payment_settings = MakerspacePaymentSettings(makerspace=makerspace)
        payment_settings.set_stripe_secret_key("sk_unreadable")
        payment_settings.set_stripe_webhook_secret("whsec_readable")
        payment_settings.save()

    if unreadable == "missing-key":
        settings.API_CLIENT_ENC_KEY = ""
        replacement = ""
    else:
        MakerspacePaymentSettings.objects.filter(pk=payment_settings.pk).update(
            stripe_secret_key="fernet:corrupt-ciphertext"
        )
        replacement = "sk_recovered"
    payment_settings.refresh_from_db()
    return makerspace, manager, payment_settings, replacement


@pytest.mark.parametrize("unreadable", ["missing-key", "corrupt-ciphertext"])
@pytest.mark.parametrize("pending", [False, True])
def test_api_recovers_unreadable_raw_credential_unless_session_is_pending(
    settings, unreadable, pending
):
    makerspace, manager, payment_settings, replacement = unreadable_raw_settings(
        settings, f"raw-api-recovery-{unreadable}-{pending}", unreadable, pending=pending
    )
    original_ciphertext = payment_settings.stripe_secret_key
    client = APIClient()
    client.force_authenticate(manager)

    response = client.patch(
        f"/api/v1/admin/makerspace/{makerspace.id}/payment-settings",
        {"stripe_secret_key": replacement},
        format="json",
    )

    payment_settings.refresh_from_db()
    if pending:
        assert response.status_code == 400
        assert "pending" in str(response.data["stripe_secret_key"]).lower()
        assert payment_settings.stripe_secret_key == original_ciphertext
    else:
        assert response.status_code == 200
        if replacement:
            assert payment_settings.get_stripe_secret_key() == replacement
        else:
            assert payment_settings.stripe_secret_key == ""


@pytest.mark.parametrize("unreadable", ["missing-key", "corrupt-ciphertext"])
@pytest.mark.parametrize("pending", [False, True])
def test_admin_recovers_unreadable_raw_credential_unless_session_is_pending(
    settings, unreadable, pending
):
    makerspace, _, payment_settings, replacement = unreadable_raw_settings(
        settings,
        f"raw-admin-recovery-{unreadable}-{pending}",
        unreadable,
        pending=pending,
    )
    original_ciphertext = payment_settings.stripe_secret_key
    form_class = admin.site._registry[MakerspacePaymentSettings].form
    form = form_class(
        data={
            "makerspace": makerspace.id,
            "stripe_publishable_key": "",
            "stripe_secret_key": replacement,
            "stripe_webhook_secret": "",
            "default_currency": "usd",
        },
        instance=payment_settings,
    )

    if pending:
        assert not form.is_valid()
        assert "pending" in str(form.errors["stripe_secret_key"]).lower()
        payment_settings.refresh_from_db()
        assert payment_settings.stripe_secret_key == original_ciphertext
    else:
        assert form.is_valid(), form.errors
        form.save()
        payment_settings.refresh_from_db()
        if replacement:
            assert payment_settings.get_stripe_secret_key() == replacement
        else:
            assert payment_settings.stripe_secret_key == ""


def test_api_preserves_omitted_raw_credentials_while_session_is_pending():
    makerspace, manager, payment_settings = pending_raw_settings(
        "payment-rotation-omit"
    )
    client = APIClient()
    client.force_authenticate(manager)

    response = client.patch(
        f"/api/v1/admin/makerspace/{makerspace.id}/payment-settings",
        {"default_currency": "INR"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["default_currency"] == "inr"
    payment_settings.refresh_from_db()
    assert payment_settings.get_stripe_secret_key() == "sk_raw"
    assert payment_settings.get_stripe_webhook_secret() == "whsec_raw"


def test_api_rejects_malformed_default_currency():
    makerspace = make_space("payment-invalid-currency")
    manager = make_member("payment-invalid-currency-manager", makerspace)
    client = APIClient()
    client.force_authenticate(manager)

    response = client.patch(
        f"/api/v1/admin/makerspace/{makerspace.id}/payment-settings",
        {"default_currency": "1$%"},
        format="json",
    )

    assert response.status_code == 400
    assert "default_currency" in response.data
    assert MakerspacePaymentSettings.objects.get(
        makerspace=makerspace
    ).default_currency == "usd"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stripe_secret_key", "sk_raw_rotated"),
        ("stripe_webhook_secret", "whsec_raw_rotated"),
    ],
)
def test_admin_blocks_raw_credential_change_while_session_is_pending(field, value):
    makerspace, _, payment_settings = pending_raw_settings(
        f"payment-admin-rotation-{field}"
    )
    form_class = admin.site._registry[MakerspacePaymentSettings].form
    data = {
        "makerspace": makerspace.id,
        "stripe_publishable_key": "",
        "stripe_secret_key": "",
        "stripe_webhook_secret": "",
        "default_currency": "usd",
    }
    data[field] = value

    form = form_class(data=data, instance=payment_settings)

    assert not form.is_valid()
    assert "pending" in str(form.errors[field]).lower()


def test_admin_preserves_blank_raw_credentials_while_session_is_pending():
    makerspace, _, payment_settings = pending_raw_settings("payment-admin-omit")
    form_class = admin.site._registry[MakerspacePaymentSettings].form
    form = form_class(
        data={
            "makerspace": makerspace.id,
            "stripe_publishable_key": "",
            "stripe_secret_key": "",
            "stripe_webhook_secret": "",
            "default_currency": "usd",
        },
        instance=payment_settings,
    )

    assert form.is_valid(), form.errors
    form.save()
    payment_settings.refresh_from_db()
    assert payment_settings.get_stripe_secret_key() == "sk_raw"
    assert payment_settings.get_stripe_webhook_secret() == "whsec_raw"
