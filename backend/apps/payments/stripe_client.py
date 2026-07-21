"""Lazy Stripe integration helpers with no process-global credential mutation."""

from importlib import import_module

from apps.payments.models import MakerspacePaymentSettings


class PaymentsUnavailable(Exception):
    """Raised when a payment operation cannot safely use Stripe."""


class StripeWebhookSignatureError(Exception):
    """Raised only when Stripe rejects a webhook signature."""


def _stripe_module():
    return import_module("stripe")


def _payment_settings(makerspace_or_settings):
    if hasattr(makerspace_or_settings, "get_stripe_secret_key"):
        return makerspace_or_settings
    return MakerspacePaymentSettings.for_makerspace(makerspace_or_settings)


def build_client(makerspace_or_settings):
    """Build a fresh client for this request without setting ``stripe.api_key``."""
    payment_settings = _payment_settings(makerspace_or_settings)
    if not payment_settings.is_configured:
        raise PaymentsUnavailable("Stripe is not configured for this makerspace.")
    try:
        secret_key = payment_settings.get_stripe_secret_key()
    except Exception as exc:
        raise PaymentsUnavailable("Stripe is not configured for this makerspace.") from exc
    if not secret_key:
        raise PaymentsUnavailable("Stripe is not configured for this makerspace.")
    return _stripe_module().StripeClient(api_key=secret_key)


def create_checkout_session(makerspace_or_settings, **params):
    """Create a Checkout Session through a makerspace-specific client (for C.3)."""
    return build_client(makerspace_or_settings).v1.checkout.sessions.create(params=params)


def expire_checkout_session(makerspace_or_settings, session_id):
    """Best-effort expiry for a Checkout Session no longer payable locally."""
    try:
        return build_client(makerspace_or_settings).v1.checkout.sessions.expire(session_id)
    except Exception:
        # Stripe returns an error when a session was already paid or expired.  The
        # local terminal reconciliation remains authoritative in either case.
        return None


def construct_event(payload, sig_header, webhook_secret):
    """Verify and parse a Stripe event without configuring a global API key."""
    if not webhook_secret:
        raise PaymentsUnavailable("Stripe webhook verification is not configured.")
    stripe = _stripe_module()
    try:
        return stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as exc:
        signature_errors = tuple(
            error
            for error in (
                getattr(stripe, "SignatureVerificationError", None),
                getattr(getattr(stripe, "error", None), "SignatureVerificationError", None),
            )
            if isinstance(error, type) and issubclass(error, Exception)
        )
        if signature_errors and isinstance(exc, signature_errors):
            raise StripeWebhookSignatureError("Invalid Stripe webhook signature.") from exc
        raise
