from dataclasses import dataclass

from apps.makerspaces.domain_verification import is_self_host
from apps.payments.models_settings import (
    MakerspacePaymentSettings,
    PlatformStripeConnectSettings,
)


@dataclass(frozen=True)
class PaymentSource:
    provider: str
    secret_key: str
    webhook_secret: str
    publishable_key: str = ""
    connected_account_id: str | None = None
    application_fee_bps: int = 0


def resolve_payment_source(makerspace) -> PaymentSource | None:
    merchant = MakerspacePaymentSettings.for_makerspace(makerspace)
    if merchant.raw_credentials_configured:
        try:
            secret_key = merchant.get_stripe_secret_key()
            webhook_secret = merchant.get_stripe_webhook_secret()
        except Exception:
            return None
        if secret_key and webhook_secret:
            return PaymentSource(
                "raw",
                secret_key,
                webhook_secret,
                publishable_key=merchant.stripe_publishable_key,
            )

    if is_self_host():
        return None
    if not (
        merchant.connect_account_id
        and merchant.connect_status == MakerspacePaymentSettings.ConnectStatus.ACTIVE
        and merchant.connect_charges_enabled
    ):
        return None
    platform = PlatformStripeConnectSettings.load()
    if not platform.is_configured:
        return None
    try:
        secret_key = platform.get_stripe_secret_key()
        webhook_secret = platform.get_stripe_webhook_secret()
    except Exception:
        return None
    if not secret_key or not webhook_secret:
        return None
    return PaymentSource(
        "connect",
        secret_key,
        webhook_secret,
        publishable_key=platform.stripe_publishable_key,
        connected_account_id=merchant.connect_account_id,
        application_fee_bps=platform.application_fee_bps,
    )


def source_for_payment(payment) -> PaymentSource | None:
    if payment.stripe_provider == payment.StripeProvider.RAW:
        merchant = MakerspacePaymentSettings.for_makerspace(payment.makerspace)
        if not merchant.raw_credentials_configured:
            return None
        try:
            return PaymentSource(
                "raw",
                merchant.get_stripe_secret_key(),
                merchant.get_stripe_webhook_secret(),
                publishable_key=merchant.stripe_publishable_key,
            )
        except Exception:
            return None
    if is_self_host() or not payment.stripe_connected_account_id:
        return None
    platform = PlatformStripeConnectSettings.load()
    if not platform.is_configured:
        return None
    try:
        return PaymentSource(
            "connect",
            platform.get_stripe_secret_key(),
            platform.get_stripe_webhook_secret(),
            publishable_key=platform.stripe_publishable_key,
            connected_account_id=payment.stripe_connected_account_id,
        )
    except Exception:
        return None
