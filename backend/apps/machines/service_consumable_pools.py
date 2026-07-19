"""Row-locked accounting authority for pooled machine consumables."""

from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit
from apps.machines.models import (
    Machine,
    MachineConsumableAdjustment,
    MachineConsumablePool,
    MachineServiceRequest,
    MachineUsageEntry,
)


def _grams(value, field):
    try:
        parsed = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: "Enter a valid gram amount."}) from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValidationError({field: "Enter a non-negative gram amount."})
    return parsed


def _audit(actor, action, pool, *, target=None, **meta):
    audit.record(actor, action, makerspace=pool.makerspace, target=target or pool, meta=meta)


@transaction.atomic
def create_pool(makerspace, actor, *, material, initial_grams, machine=None, color="", brand="", lot_code="", low_threshold_grams=None):
    initial = _grams(initial_grams, "initial_grams")
    if not str(material).strip():
        raise ValidationError({"material": "Material is required."})
    if machine is not None:
        machine = Machine.objects.select_for_update().get(pk=machine.pk)
        if machine.makerspace_id != makerspace.pk:
            raise ValidationError({"machine": "Machine must belong to this makerspace."})
    threshold = None if low_threshold_grams is None else _grams(low_threshold_grams, "low_threshold_grams")
    pool = MachineConsumablePool.objects.create(
        makerspace=makerspace, machine=machine, material=str(material).strip(), color=str(color).strip(),
        brand=str(brand).strip(), lot_code=str(lot_code).strip(), initial_grams=initial,
        remaining_grams=initial, low_threshold_grams=threshold, created_by=actor,
    )
    _audit(actor, "machine_consumable_pool.created", pool, pool_id=pool.pk, initial_grams=str(initial))
    return pool


def _locked_pool(pool):
    return MachineConsumablePool.objects.select_for_update(of=("self",)).select_related("makerspace", "machine").get(pk=pool.pk)


def _apply(pool, actor, *, kind, delta, service_request=None, usage_entry=None, reason=""):
    delta = Decimal(delta).quantize(Decimal("0.01"))
    after = pool.remaining_grams + delta
    if after < 0:
        raise ValidationError({"grams": f"Only {pool.remaining_grams} grams remain."})
    if after > pool.initial_grams:
        raise ValidationError({"grams": "Adjustment would exceed initial grams."})
    row = MachineConsumableAdjustment.objects.create(
        consumable_pool=pool, makerspace=pool.makerspace, kind=kind, quantity_delta=delta,
        service_request=service_request, usage_entry=usage_entry, reason=str(reason).strip(), created_by=actor,
    )
    pool.remaining_grams = after
    pool.save(update_fields=["remaining_grams", "updated_at"])
    _audit(actor, f"machine_consumable_pool.{kind}", pool, target=row, pool_id=pool.pk,
           adjustment_id=row.pk, quantity_delta=str(delta), remaining_grams=str(after),
           request_id=getattr(service_request, "pk", None), usage_entry_id=getattr(usage_entry, "pk", None))
    return row


@transaction.atomic
def reserve_for_request(service_request, actor, *, pool, planned_grams, machine):
    request = MachineServiceRequest.objects.select_for_update(of=("self",)).select_related("queue__makerspace", "bucket__machine__makerspace").get(pk=service_request.pk)
    locked = _locked_pool(pool)
    planned = _grams(planned_grams, "planned_grams")
    if not planned:
        raise ValidationError({"planned_grams": "Planned grams must be greater than zero."})
    if not locked.is_active:
        raise ValidationError({"consumable_pool": "Consumable pool is retired."})
    if locked.makerspace_id != request.makerspace_id or (locked.machine_id and locked.machine_id != machine.pk):
        raise ValidationError({"consumable_pool": "Consumable pool is incompatible with this machine service request."})
    if request.reserved_grams:
        raise ValidationError({"planned_grams": "Consumable grams are already reserved."})
    _apply(locked, actor, kind=MachineConsumableAdjustment.Kind.RESERVE, delta=-planned, service_request=request)
    request.run_consumable_pool = locked
    request.planned_grams = planned
    request.reserved_grams = planned
    request.save(update_fields=["run_consumable_pool", "planned_grams", "reserved_grams", "updated_at"])
    return request


@transaction.atomic
def reconcile_request(service_request, actor, *, actual_grams, reason=""):
    request = MachineServiceRequest.objects.select_for_update(of=("self",)).select_related("run_consumable_pool", "queue__makerspace", "bucket__machine__makerspace").get(pk=service_request.pk)
    if request.run_consumable_pool_id is None:
        return request
    actual = _grams(actual_grams, "actual_grams")
    pool = _locked_pool(request.run_consumable_pool)
    delta = request.reserved_grams - actual
    if delta:
        _apply(pool, actor, kind=MachineConsumableAdjustment.Kind.RECONCILE, delta=delta, service_request=request, reason=reason)
    request.actual_consumed_grams = actual
    request.reserved_grams = Decimal("0")
    request.save(update_fields=["actual_consumed_grams", "reserved_grams", "updated_at"])
    return request


@transaction.atomic
def correct_pool(pool, actor, *, quantity_delta, reason):
    if not str(reason).strip():
        raise ValidationError({"reason": "A correction reason is required."})
    locked = _locked_pool(pool)
    signed = _signed_grams(quantity_delta, "quantity_delta")
    delta = abs(signed)
    if signed < 0:
        delta = -delta
    if not delta:
        raise ValidationError({"quantity_delta": "Adjustment cannot be zero."})
    _apply(locked, actor, kind=MachineConsumableAdjustment.Kind.CORRECTION, delta=delta, reason=reason)
    return locked


def _signed_grams(value, field):
    try:
        parsed = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: "Enter a valid gram amount."}) from exc
    if not parsed.is_finite():
        raise ValidationError({field: "Enter a finite gram amount."})
    return parsed


@transaction.atomic
def retire_pool(pool, actor, *, reason):
    if not str(reason).strip():
        raise ValidationError({"reason": "A retirement reason is required."})
    locked = _locked_pool(pool)
    if not locked.is_active:
        return locked
    if locked.remaining_grams:
        _apply(locked, actor, kind=MachineConsumableAdjustment.Kind.RETIRE, delta=-locked.remaining_grams, reason=reason)
    locked.is_active = False
    locked.save(update_fields=["is_active", "updated_at"])
    _audit(actor, "machine_consumable_pool.retired", locked, pool_id=locked.pk)
    return locked


@transaction.atomic
def log_typed_manual_usage(machine, actor, *, duration_minutes, outcome, percent_complete, reason="", grams=0, pool=None, service_request=None, note=""):
    machine = Machine.objects.select_for_update().select_related("makerspace").get(pk=machine.pk)
    if outcome not in {"success", "failed"}:
        raise ValidationError({"outcome": "Outcome must be success or failed."})
    if not isinstance(duration_minutes, int) or duration_minutes < 0:
        raise ValidationError({"duration_minutes": "Duration must be a non-negative whole number."})
    if not isinstance(percent_complete, int) or not 0 <= percent_complete <= 100:
        raise ValidationError({"percent_complete": "Percent must be between 0 and 100."})
    if outcome == "failed" and not str(reason).strip():
        raise ValidationError({"reason": "A failure reason is required."})
    grams = _grams(grams, "grams")
    if pool is not None:
        pool = _locked_pool(pool)
        if pool.makerspace_id != machine.makerspace_id or (pool.machine_id and pool.machine_id != machine.pk):
            raise ValidationError({"consumable_pool": "Consumable pool is incompatible with this machine."})
    if service_request is not None:
        service_request = MachineServiceRequest.objects.select_for_update().get(pk=service_request.pk)
        if service_request.makerspace_id != machine.makerspace_id:
            raise ValidationError({"service_request": "Service request must belong to this makerspace."})
    entry = MachineUsageEntry.objects.create(
        machine=machine, hours=(Decimal(duration_minutes) * Decimal(percent_complete) / Decimal("6000")).quantize(Decimal("0.01")),
        source=MachineUsageEntry.Source.TYPED_MANUAL, service_request=service_request, consumable_pool=pool,
        duration_minutes=duration_minutes, outcome=outcome, percent_complete=percent_complete,
        reason=str(reason).strip(), consumed_grams=grams, note=str(note).strip(), logged_by=actor,
    )
    if grams:
        if pool is None:
            raise ValidationError({"consumable_pool": "A consumable pool is required when grams are recorded."})
        _apply(pool, actor, kind=MachineConsumableAdjustment.Kind.MANUAL, delta=-grams, usage_entry=entry, service_request=service_request, reason=reason)
    audit.record(
        actor, "machine.typed_usage_logged", makerspace=machine.makerspace, target=entry,
        meta={"machine_id": machine.pk, "usage_entry_id": entry.pk, "duration_minutes": duration_minutes,
              "outcome": outcome, "grams": str(grams)},
    )
    return entry
