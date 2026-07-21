"""Machine-service charging boundary; payment failures never affect fulfilment."""

from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.payments.availability import online_payments_enabled
from apps.payments.models import Payment
from apps.payments.services import create_checkout, create_payment


def create_for_completed_request(service_request, actor):
    try:
        with transaction.atomic():
            machine_type = service_request.assigned_machine.machine_type
            config = machine_type.capability_config or {}
            if not online_payments_enabled(service_request.makerspace, "machines"):
                return None
            if not {"rate_per_unit", "flat_fee", "currency"}.issubset(config):
                return None
            quantity = service_request.actual_consumed_quantity
            if quantity is None:
                quantity = service_request.actual_consumed_grams
            amount = (_decimal(quantity) * _decimal(config["rate_per_unit"]) + _decimal(config["flat_fee"])).quantize(Decimal("0.01"))
            if amount <= 0:
                return None
            payment = create_payment(makerspace=service_request.makerspace, subject_type=Payment.SubjectType.MACHINE_SERVICE_REQUEST, subject_id=service_request.pk, member=service_request.member or service_request.requester, amount=amount, currency=config["currency"], created_by=actor)
    except Exception:
        return None
    try:
        create_checkout(payment)
    except Exception:
        pass
    return payment


def _decimal(value):
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
    return parsed if parsed.is_finite() else Decimal("0")
