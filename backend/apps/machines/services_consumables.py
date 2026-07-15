"""Audited, row-locked mutations for machine consumables."""
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.services import record
from apps.inventory import availability
from apps.inventory.models import InventoryProduct, TrackingMode
from apps.machines import access
from apps.machines.models import Machine, MachineConsumable


def _audit(machine, actor, action, meta):
    record(
        actor,
        action,
        makerspace=machine.makerspace,
        target=machine,
        target_type="machine",
        meta=meta,
    )


def _active(machine):
    if not machine.is_active:
        raise ValidationError("Machine is retired.")


def _decimal(value, field):
    try:
        value = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field: "Enter a valid quantity."}) from None
    if not value.is_finite():
        raise ValidationError({field: "Enter a finite quantity."})
    return value


@transaction.atomic
def link_consumable(
    machine,
    actor,
    *,
    measurement,
    product=None,
    label="",
    remaining=Decimal("0"),
    low_threshold=None,
    note="",
):
    if not access.can_manage_machine(actor, machine):
        raise PermissionDenied()
    machine = Machine.objects.select_for_update().select_related("makerspace").get(
        pk=machine.pk
    )
    _active(machine)
    if measurement not in MachineConsumable.Measurement.values:
        raise ValidationError({"measurement": "Invalid measurement."})

    label = label.strip()
    if measurement == MachineConsumable.Measurement.COUNT:
        if product is None:
            raise ValidationError({"product_id": "A product is required for count mode."})
        product = InventoryProduct.objects.select_for_update().filter(pk=product.pk).first()
        if product is None or product.makerspace_id != machine.makerspace_id:
            raise ValidationError({"product_id": "Product must belong to this makerspace."})
        if product.is_archived:
            raise ValidationError({"product_id": "Archived products cannot be linked."})
        if product.tracking_mode != TrackingMode.QUANTITY:
            raise ValidationError({"product_id": "Only quantity-tracked products can be linked."})
        label = ""
        remaining = Decimal("0")
    else:
        if product is not None:
            raise ValidationError({"product_id": "Gram consumables are not inventory products."})
        if not label:
            raise ValidationError({"label": "A label is required for grams mode."})
        remaining = _decimal(remaining, "remaining")
        if remaining < 0:
            raise ValidationError({"remaining": "Remaining grams cannot be negative."})

    if low_threshold is not None:
        low_threshold = _decimal(low_threshold, "low_threshold")
    if low_threshold is not None and low_threshold < 0:
        raise ValidationError({"low_threshold": "Low threshold cannot be negative."})
    try:
        row = MachineConsumable.objects.create(
            machine=machine,
            measurement=measurement,
            product=product,
            label=label,
            remaining=remaining,
            low_threshold=low_threshold,
            note=note.strip(),
            created_by=actor,
        )
    except IntegrityError:
        raise ValidationError({"product_id": "This product is already linked."}) from None
    _audit(
        machine,
        actor,
        "machine.consumable_linked",
        {
            "consumable_id": row.pk,
            "measurement": measurement,
            "product_id": row.product_id,
            "label": row.label,
        },
    )
    return row


@transaction.atomic
def unlink_consumable(machine, actor, consumable):
    if not access.can_manage_machine(actor, machine):
        raise PermissionDenied()
    machine = Machine.objects.select_for_update().select_related("makerspace").get(
        pk=machine.pk
    )
    row = MachineConsumable.objects.select_for_update(of=("self",)).filter(
        pk=consumable.pk, machine=machine
    ).first()
    if row is None:
        raise ValidationError("Consumable is not linked to this machine.")
    meta = {
        "consumable_id": row.pk,
        "measurement": row.measurement,
        "product_id": row.product_id,
        "label": row.label,
    }
    row.delete()
    _audit(machine, actor, "machine.consumable_unlinked", meta)


@transaction.atomic
def log_consumption(machine, actor, consumable, quantity):
    if not access.can_operate_machine(actor, machine):
        raise PermissionDenied()
    machine = Machine.objects.select_for_update().select_related("makerspace").get(
        pk=machine.pk
    )
    _active(machine)
    row = (
        MachineConsumable.objects.select_for_update(of=("self",))
        .select_related("product")
        .filter(pk=consumable.pk, machine=machine)
        .first()
    )
    if row is None:
        raise ValidationError("Consumable is not linked to this machine.")
    quantity = _decimal(quantity, "quantity")
    if quantity <= 0:
        raise ValidationError({"quantity": "Quantity must be greater than zero."})

    if row.measurement == MachineConsumable.Measurement.COUNT:
        if quantity != quantity.to_integral_value():
            raise ValidationError({"quantity": "Count consumption must be a whole number."})
        row.product = availability.consume_available(
            row.product,
            int(quantity),
            reason=f"Consumed by machine {machine.pk}: {machine.name}",
            actor=actor,
        )
    else:
        if row.remaining < quantity:
            raise ValidationError({"quantity": f"Only {row.remaining} grams remain."})
        row.remaining -= quantity
        row.save(update_fields=["remaining"])

    meta = {"measurement": row.measurement, "quantity": str(quantity)}
    if row.product_id:
        meta["product_id"] = row.product_id
    else:
        meta["label"] = row.label
    _audit(machine, actor, "machine.consumption_logged", meta)
    return row
