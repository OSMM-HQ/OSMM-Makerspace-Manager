"""Atomic service-request consumption debit authority."""

from decimal import Decimal, InvalidOperation

from apps.audit import services as audit
from apps.inventory import availability
from apps.inventory.availability import InsufficientStock
from apps.machines.models import MachineConsumable, ServiceRequestConsumption
from apps.machines.service_errors import (
    ServiceConsumptionInvalid,
    ServiceInsufficientStock,
)


def debit_consumptions(service_request, actor, consumptions, *, outcome):
    """Debit submitted actual use while the caller holds the request row lock."""
    if outcome not in ServiceRequestConsumption.Outcome.values:
        raise ServiceConsumptionInvalid("Consumption outcome is invalid.")
    if not isinstance(consumptions, list):
        raise ServiceConsumptionInvalid("Consumptions must be a list.")
    if not service_request.assigned_machine_id:
        raise ServiceConsumptionInvalid("A machine must be assigned before consumption.")

    parsed = [_parse(row) for row in consumptions]
    ids = [row[0] for row in parsed]
    if len(ids) != len(set(ids)):
        raise ServiceConsumptionInvalid("A consumable may appear only once.")
    if not ids:
        return []

    rows = list(
        MachineConsumable.objects.select_for_update(of=("self",))
        .select_related("product")
        .filter(pk__in=ids, machine_id=service_request.assigned_machine_id)
        .order_by("id")
    )
    by_id = {row.pk: row for row in rows}
    if len(by_id) != len(ids):
        raise ServiceConsumptionInvalid("Consumable is not linked to the assigned machine.")
    if ServiceRequestConsumption.objects.filter(
        service_request=service_request, machine_consumable_id__in=ids
    ).exists():
        raise ServiceConsumptionInvalid("Consumption has already been recorded for this request.")

    created = []
    for consumable_id, quantity in parsed:
        row = by_id[consumable_id]
        if row.measurement == MachineConsumable.Measurement.COUNT:
            _debit_count(service_request, actor, row, quantity)
            snapshot = ServiceRequestConsumption.objects.create(
                service_request=service_request,
                machine_consumable=row,
                measurement=ServiceRequestConsumption.Measurement.COUNT,
                product=row.product,
                quantity=quantity,
                created_by=actor,
                outcome=outcome,
            )
        else:
            _debit_grams(row, quantity)
            snapshot = ServiceRequestConsumption.objects.create(
                service_request=service_request,
                machine_consumable=row,
                measurement=ServiceRequestConsumption.Measurement.GRAMS,
                label=row.label,
                quantity=quantity,
                created_by=actor,
                outcome=outcome,
            )
        created.append(snapshot)

    audit.record(
        actor,
        "machine_service.consumption_recorded",
        makerspace=service_request.bucket.machine.makerspace,
        target=service_request,
        meta={
            "request_id": service_request.pk,
            "status": service_request.status,
            "outcome": outcome,
            "consumptions": [
                {"machine_consumable_id": row.machine_consumable_id, "quantity": str(row.quantity)}
                for row in created
            ],
        },
    )
    return created


def _parse(value):
    if not isinstance(value, dict):
        raise ServiceConsumptionInvalid("Each consumption must be an object.")
    consumable_id = value.get("machine_consumable_id")
    if isinstance(consumable_id, bool):
        raise ServiceConsumptionInvalid("machine_consumable_id is required.")
    try:
        consumable_id = int(consumable_id)
    except (TypeError, ValueError) as exc:
        raise ServiceConsumptionInvalid("machine_consumable_id is required.") from exc
    if consumable_id <= 0:
        raise ServiceConsumptionInvalid("machine_consumable_id is required.")
    try:
        quantity = Decimal(str(value.get("quantity")))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ServiceConsumptionInvalid("Consumption quantity must be numeric.") from exc
    if not quantity.is_finite() or quantity <= 0:
        raise ServiceConsumptionInvalid("Consumption quantity must be positive.")
    return consumable_id, quantity.quantize(Decimal("0.01"))


def _debit_count(service_request, actor, row, quantity):
    if quantity != quantity.to_integral_value():
        raise ServiceConsumptionInvalid("Count consumption must be a whole number.")
    try:
        availability.consume_available(
            row.product,
            int(quantity),
            reason=f"Machine service request {service_request.pk} consumption",
            actor=actor,
        )
    except InsufficientStock as exc:
        raise ServiceInsufficientStock(str(exc)) from exc


def _debit_grams(row, quantity):
    if row.remaining < quantity:
        raise ServiceInsufficientStock(f"Only {row.remaining} grams remain.")
    row.remaining -= quantity
    row.save(update_fields=["remaining"])
