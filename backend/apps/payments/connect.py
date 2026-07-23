import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.makerspaces.models import Makerspace
from apps.audit import services as audit
from apps.payments.models import (
    MakerspacePaymentSettings,
    Payment,
    PlatformStripeConnectSettings,
    StripeConnectOAuthState,
)
from apps.payments.stripe_client import PaymentsUnavailable


STRIPE_AUTHORIZE_URL = "https://connect.stripe.com/oauth/authorize"


def state_digest(raw_state):
    return hashlib.sha256(raw_state.encode("utf-8")).hexdigest()


def oauth_state_is_latest(oauth_state):
    latest_id = (
        StripeConnectOAuthState.objects.filter(
            makerspace_id=oauth_state.makerspace_id
        )
        .order_by("-created_at", "-pk")
        .values_list("pk", flat=True)
        .first()
    )
    return latest_id == oauth_state.pk


def account_has_pending_payments(account_id):
    return Payment.objects.filter(
        stripe_provider=Payment.StripeProvider.CONNECT,
        stripe_connected_account_id=account_id,
        status=Payment.Status.PENDING,
    ).exists()


def create_onboarding(makerspace, actor):
    platform = PlatformStripeConnectSettings.load()
    redirect_uri = str(settings.STRIPE_CONNECT_REDIRECT_URI or "").strip()
    if not platform.is_configured or not redirect_uri:
        raise PaymentsUnavailable("Stripe Connect is not configured.")
    raw_state = secrets.token_urlsafe(32)
    with transaction.atomic():
        # Serialize onboarding generations with callback assignment. A callback
        # that already exchanged its code must re-check the latest state while
        # holding this same makerspace lock before it can assign an account.
        Makerspace.objects.select_for_update().get(pk=makerspace.pk)
        StripeConnectOAuthState.objects.create(
            makerspace=makerspace,
            initiated_by=actor,
            state_digest=state_digest(raw_state),
            expires_at=timezone.now() + timedelta(minutes=10),
        )
    query = urlencode(
        {
            "response_type": "code",
            "client_id": platform.stripe_connect_client_id,
            "scope": "read_write",
            "redirect_uri": redirect_uri,
            "state": raw_state,
        }
    )
    return f"{STRIPE_AUTHORIZE_URL}?{query}"


def _platform_client():
    from apps.payments.stripe_client import _stripe_module

    platform = PlatformStripeConnectSettings.load()
    if not platform.is_configured:
        raise PaymentsUnavailable("Stripe Connect is not configured.")
    return _stripe_module().StripeClient(api_key=platform.get_stripe_secret_key())


def exchange_oauth_code(code):
    response = _platform_client().oauth.token(
        params={"grant_type": "authorization_code", "code": code}
    )
    account_id = _value(response, "stripe_user_id")
    if not account_id:
        raise PaymentsUnavailable("Stripe did not return a connected account.")
    return account_id


def deauthorize_account(account_id):
    platform = PlatformStripeConnectSettings.load()
    if not platform.stripe_connect_client_id:
        raise PaymentsUnavailable("Stripe Connect is not configured.")
    _platform_client().oauth.deauthorize(
        params={
            "client_id": platform.stripe_connect_client_id,
            "stripe_user_id": account_id,
        }
    )


def rollback_oauth_mapping(
    *, makerspace, actor, oauth_state, account_id, previous
):
    """Revoke a newly granted account and restore the prior local mapping."""
    try:
        deauthorize_account(account_id)
    except Exception:
        restrict_oauth_mapping(
            makerspace=makerspace,
            actor=actor,
            oauth_state=oauth_state,
            account_id=account_id,
            action="payments.connect_authorization_revoke_failed",
        )
        return False

    with transaction.atomic():
        merchant = (
            MakerspacePaymentSettings.objects.select_for_update()
            .filter(makerspace=makerspace, connect_account_id=account_id)
            .first()
        )
        if merchant is not None:
            for field, value in previous.items():
                setattr(merchant, field, value)
            merchant.save(update_fields=list(previous))
        audit.record(
            actor,
            "payments.connect_authorization_revoked",
            makerspace=makerspace,
            target=oauth_state,
            meta={"connect_account_id": account_id},
        )
    return True


def restrict_oauth_mapping(
    *, makerspace, actor, oauth_state, account_id, action="payments.connect_onboarding_failed"
):
    with transaction.atomic():
        merchant = (
            MakerspacePaymentSettings.objects.select_for_update()
            .filter(makerspace=makerspace, connect_account_id=account_id)
            .first()
        )
        if merchant is not None:
            merchant.connect_status = MakerspacePaymentSettings.ConnectStatus.RESTRICTED
            merchant.connect_charges_enabled = False
            merchant.connect_payouts_enabled = False
            merchant.save(
                update_fields=[
                    "connect_status",
                    "connect_charges_enabled",
                    "connect_payouts_enabled",
                ]
            )
        audit.record(
            actor,
            action,
            makerspace=makerspace,
            target=oauth_state,
            meta={"connect_account_id": account_id},
        )


def fetch_account(account_id):
    try:
        return _platform_client().v1.accounts.retrieve(account_id)
    except PaymentsUnavailable:
        raise
    except Exception as exc:
        raise PaymentsUnavailable("Stripe Connect account is unavailable.") from exc


def update_account_status(merchant, account):
    charges_enabled = bool(_value(account, "charges_enabled"))
    payouts_enabled = bool(_value(account, "payouts_enabled"))
    details_submitted = bool(_value(account, "details_submitted"))
    merchant.connect_charges_enabled = charges_enabled
    merchant.connect_payouts_enabled = payouts_enabled
    merchant.connect_status = (
        MakerspacePaymentSettings.ConnectStatus.ACTIVE
        if charges_enabled
        else MakerspacePaymentSettings.ConnectStatus.RESTRICTED
        if details_submitted
        else MakerspacePaymentSettings.ConnectStatus.PENDING
    )
    merchant.connect_status_updated_at = timezone.now()
    # The Stripe fetch above is remote latency. Persist only status fields so this
    # possibly stale instance can never overwrite credentials, currency, or account ID.
    merchant.save(
        update_fields=[
            "connect_status",
            "connect_charges_enabled",
            "connect_payouts_enabled",
            "connect_status_updated_at",
        ]
    )
    return merchant


def restrict_account_status(merchant):
    """Fail closed when Stripe cannot authoritatively refresh an account."""
    merchant.connect_status = MakerspacePaymentSettings.ConnectStatus.RESTRICTED
    merchant.connect_charges_enabled = False
    merchant.connect_payouts_enabled = False
    merchant.connect_status_updated_at = timezone.now()
    merchant.save(
        update_fields=[
            "connect_status",
            "connect_charges_enabled",
            "connect_payouts_enabled",
            "connect_status_updated_at",
        ]
    )
    return merchant


def refresh_connected_account(merchant):
    if not merchant.connect_account_id:
        raise PaymentsUnavailable("Stripe Connect account is unavailable.")
    return update_account_status(merchant, fetch_account(merchant.connect_account_id))


def _value(value, key):
    return value.get(key) if isinstance(value, dict) else getattr(value, key, None)
