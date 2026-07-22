"""Payment mutation and Stripe reconciliation boundary."""

import logging
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.makerspaces.platform import member_area_url
from apps.payments import stripe_client
from apps.payments.connect import refresh_connected_account, restrict_account_status
from apps.payments.models import (
    MakerspacePaymentSettings,
    Payment,
    PlatformStripeConnectSettings,
)
from apps.payments.resolution import resolve_payment_source, source_for_payment
from apps.payments.services_webhooks import (
    apply_connect_webhook_event,
    apply_webhook_event,
)

logger = logging.getLogger(__name__)


class _ConnectAccountCannotCharge(Exception):
    def __init__(self, merchant_id):
        self.merchant_id = merchant_id


def create_payment(*, makerspace, subject_type, subject_id, member, amount, currency, created_by):
    source = resolve_payment_source(makerspace)
    if source is None:
        raise stripe_client.PaymentsUnavailable(
            "Payments are not configured for this makerspace."
        )
    provider = source.provider
    connected_account_id = source.connected_account_id
    fee_amount = _application_fee_amount(amount, source.application_fee_bps)
    return Payment.objects.create(
        makerspace=makerspace,
        subject_type=subject_type,
        subject_id=subject_id,
        member=member,
        amount=amount,
        currency=currency.lower(),
        created_by=created_by,
        stripe_provider=provider,
        stripe_connected_account_id=connected_account_id,
        stripe_application_fee_amount=fee_amount,
    )


def create_checkout(payment):
    """Schedule checkout creation; Stripe failure is deliberately never caller-visible."""
    transaction.on_commit(lambda: _create_checkout_safely(payment.pk))


def _create_checkout_safely(payment_id):
    try:
        create_checkout_url(payment_id)
    except Exception:
        logger.exception("payment_checkout_creation_failed", extra={"payment_id": payment_id})


def create_checkout_url(payment_id):
    """Create and persist a pending payment's Checkout URL exactly once."""
    try:
        return _create_checkout_url_atomic(payment_id)
    except _ConnectAccountCannotCharge as exc:
        merchant = MakerspacePaymentSettings.objects.get(pk=exc.merchant_id)
        restrict_account_status(merchant)
        raise stripe_client.PaymentsUnavailable(
            "Stripe Connect account cannot accept charges."
        ) from None


def _create_checkout_url_atomic(payment_id):
    payment_snapshot = Payment.objects.only(
        "makerspace_id", "stripe_provider"
    ).get(pk=payment_id)
    with transaction.atomic():
        # Checkout lock order is platform settings (Connect only) -> makerspace
        # settings -> Payment. Credential updates take their corresponding
        # settings lock before checking Payment rows. Payment-only reconciliation
        # must never acquire either settings lock, keeping the order acyclic.
        if payment_snapshot.stripe_provider == Payment.StripeProvider.CONNECT:
            platform = (
                PlatformStripeConnectSettings.objects.select_for_update()
                .filter(pk=1)
                .first()
            )
            if platform is None:
                raise stripe_client.PaymentsUnavailable(
                    "Stripe Connect is not configured."
                )
        merchant = (
            MakerspacePaymentSettings.objects.select_for_update()
            .filter(makerspace_id=payment_snapshot.makerspace_id)
            .first()
        )
        payment = Payment.objects.select_for_update().select_related("makerspace").get(pk=payment_id)
        if payment.status != Payment.Status.PENDING:
            return ""
        if payment.stripe_checkout_url:
            return payment.stripe_checkout_url
        source = source_for_payment(payment)
        if source is None:
            raise stripe_client.PaymentsUnavailable("Payments are not configured.")
        if payment.stripe_provider == Payment.StripeProvider.CONNECT:
            if (
                merchant is None
                or merchant.connect_account_id
                != payment.stripe_connected_account_id
            ):
                raise stripe_client.PaymentsUnavailable(
                    "Stripe Connect account is unavailable."
                )
            refreshed = refresh_connected_account(merchant)
            if not (
                refreshed.connect_status == MakerspacePaymentSettings.ConnectStatus.ACTIVE
                and refreshed.connect_charges_enabled
            ):
                raise _ConnectAccountCannotCharge(refreshed.pk)
        member_url = member_area_url(payment.makerspace)
        if not member_url:
            logger.warning("payment_checkout_return_url_unavailable", extra={"payment_id": payment_id})
            raise stripe_client.PaymentsUnavailable("A payment return URL is not configured.")
        checkout_params = {
            "mode": "payment",
            "client_reference_id": str(payment.pk),
            "success_url": f"{member_url}?checkout=success",
            "cancel_url": f"{member_url}?checkout=cancelled",
            "metadata": {"payment_id": str(payment.pk), "makerspace_id": str(payment.makerspace_id)},
            "line_items": [{"price_data": {"currency": payment.currency, "unit_amount": int(payment.amount * 100), "product_data": {"name": "Machine service"}}, "quantity": 1}],
        }
        if payment.stripe_application_fee_amount:
            checkout_params["payment_intent_data"] = {
                "application_fee_amount": payment.stripe_application_fee_amount
            }
        session = stripe_client.create_checkout_session(
            source,
            idempotency_key=_checkout_idempotency_key(payment),
            **checkout_params,
        )
        session_id, checkout_url = _value(session, "id"), _value(session, "url")
        if not session_id or not checkout_url:
            raise stripe_client.PaymentsUnavailable("Stripe did not return a Checkout URL.")
        payment.stripe_checkout_session_id = session_id
        payment.stripe_checkout_url = checkout_url
        payment.stripe_checkout_session_expired_at = None
        payment.save(
            update_fields=[
                "stripe_checkout_session_id",
                "stripe_checkout_url",
                "stripe_checkout_session_expired_at",
                "updated_at",
            ]
        )
        return checkout_url


def mark_offline(payment, actor):
    return _reconcile(payment, actor, Payment.Status.PAID_OFFLINE, "payment.paid_offline")


def waive(payment, actor):
    return _reconcile(payment, actor, Payment.Status.WAIVED, "payment.waived")


def _reconcile(payment, actor, status, action):
    with transaction.atomic():
        locked = Payment.objects.select_for_update().get(pk=payment.pk)
        if locked.status == Payment.Status.PENDING:
            if locked.stripe_checkout_session_id:
                try:
                    expiry_source = source_for_payment(locked)
                    if expiry_source is None:
                        raise stripe_client.PaymentsUnavailable(
                            "The payment's Stripe source is no longer configured."
                        )
                    expiry_succeeded = stripe_client.expire_checkout_session(
                        expiry_source, locked.stripe_checkout_session_id
                    )
                    if expiry_succeeded:
                        locked.stripe_checkout_session_expired_at = timezone.now()
                except Exception:
                    logger.exception("payment_checkout_expiry_failed", extra={"payment_id": locked.pk})
            locked.status = status
            locked.save(
                update_fields=[
                    "status",
                    "stripe_checkout_session_expired_at",
                    "updated_at",
                ]
            )
            audit.record(actor, action, makerspace=locked.makerspace, target=locked)
        return locked


def _value(value, key):
    return value.get(key) if isinstance(value, dict) else getattr(value, key, None)


def _application_fee_amount(amount, basis_points):
    minor_units = (Decimal(amount) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(
        (minor_units * Decimal(basis_points) / Decimal(10000)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _checkout_idempotency_key(payment):
    generation = 0
    if payment.stripe_checkout_session_expired_at is not None:
        generation = int(
            payment.stripe_checkout_session_expired_at.timestamp() * 1_000_000
        )
    return f"payment-checkout-{payment.pk}-{generation}"
