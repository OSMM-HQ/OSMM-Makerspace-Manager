"""Payment mutation and Stripe reconciliation boundary."""

import logging
from django.db.models import Q

from django.db import IntegrityError, transaction

from apps.audit import services as audit
from apps.makerspaces.platform import member_area_url
from apps.payments import stripe_client
from apps.payments.models import Payment, ProcessedStripeEvent

logger = logging.getLogger(__name__)


def create_payment(*, makerspace, subject_type, subject_id, member, amount, currency, created_by):
    return Payment.objects.create(makerspace=makerspace, subject_type=subject_type, subject_id=subject_id, member=member, amount=amount, currency=currency.lower(), created_by=created_by)


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
    with transaction.atomic():
        payment = Payment.objects.select_for_update().select_related("makerspace").get(pk=payment_id)
        if payment.status != Payment.Status.PENDING:
            return ""
        if payment.stripe_checkout_url:
            return payment.stripe_checkout_url
        member_url = member_area_url(payment.makerspace)
        if not member_url:
            logger.warning("payment_checkout_return_url_unavailable", extra={"payment_id": payment_id})
            raise stripe_client.PaymentsUnavailable("A payment return URL is not configured.")
        session = stripe_client.create_checkout_session(
            payment.makerspace,
            mode="payment",
            client_reference_id=str(payment.pk),
            success_url=f"{member_url}?checkout=success",
            cancel_url=f"{member_url}?checkout=cancelled",
            metadata={"payment_id": str(payment.pk), "makerspace_id": str(payment.makerspace_id)},
            line_items=[{"price_data": {"currency": payment.currency, "unit_amount": int(payment.amount * 100), "product_data": {"name": "Machine service"}}, "quantity": 1}],
        )
        session_id, checkout_url = _value(session, "id"), _value(session, "url")
        if not session_id or not checkout_url:
            raise stripe_client.PaymentsUnavailable("Stripe did not return a Checkout URL.")
        payment.stripe_checkout_session_id = session_id
        payment.stripe_checkout_url = checkout_url
        payment.save(update_fields=["stripe_checkout_session_id", "stripe_checkout_url", "updated_at"])
        return checkout_url


def apply_webhook_event(makerspace, event):
    event_id = _value(event, "id")
    if not event_id:
        return None
    event_type, data = _value(event, "type"), _value(event, "data") or {}
    obj = _value(data, "object") or {}
    if event_type not in {"checkout.session.completed", "checkout.session.async_payment_succeeded", "payment_intent.succeeded"}:
        return None
    if event_type == "checkout.session.completed" and _value(obj, "payment_status") not in {"paid", None}:
        return None
    session_id = _value(obj, "id") if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"} else None
    intent_id = _value(obj, "payment_intent") or (_value(obj, "id") if event_type == "payment_intent.succeeded" else None)
    if not session_id and not intent_id:
        return None
    with transaction.atomic():
        identifiers = Q()
        if session_id:
            identifiers |= Q(stripe_checkout_session_id=session_id)
        if intent_id:
            identifiers |= Q(stripe_payment_intent_id=intent_id)
        payment = Payment.objects.select_for_update().filter(makerspace=makerspace).filter(identifiers).first()
        if payment is None:
            return None
        try:
            ProcessedStripeEvent.objects.create(makerspace=makerspace, stripe_event_id=event_id)
        except IntegrityError:
            return None
        if payment.status != Payment.Status.PENDING:
            audit.record(None, "payment.paid_after_terminal", makerspace=makerspace, target=payment, meta={"stripe_event_id": event_id, "prior_status": payment.status})
            return payment

        payment.status = Payment.Status.PAID_ONLINE
        if intent_id:
            payment.stripe_payment_intent_id = intent_id
        payment.save(update_fields=["status", "stripe_payment_intent_id", "updated_at"])
        audit.record(None, "payment.paid_online", makerspace=makerspace, target=payment, meta={"stripe_event_id": event_id})
        return payment


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
                    stripe_client.expire_checkout_session(locked.makerspace, locked.stripe_checkout_session_id)
                except Exception:
                    logger.exception("payment_checkout_expiry_failed", extra={"payment_id": locked.pk})
            locked.status = status
            locked.save(update_fields=["status", "updated_at"])
            audit.record(actor, action, makerspace=locked.makerspace, target=locked)
        return locked


def _value(value, key):
    return value.get(key) if isinstance(value, dict) else getattr(value, key, None)
