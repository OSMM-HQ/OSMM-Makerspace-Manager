from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.audit import services as audit
from apps.printing.models import FilamentAdjustment, FilamentSpool
class InvalidFilamentAdjustment(Exception):
    pass


def record_adjustment(
    *,
    actor,
    spool,
    kind,
    grams,
    reason,
    print_request=None,
    manual_log=None,
):
    value = coerce_grams(grams)
    return FilamentAdjustment.objects.create(
        filament_spool=spool,
        makerspace=spool.makerspace,
        kind=kind,
        grams=value,
        print_request=print_request,
        manual_log=manual_log,
        reason=(reason or "").strip(),
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )


def apply_staff_adjustment(actor, spool_id, *, kind, grams, reason):
    if kind not in (FilamentAdjustment.Kind.CORRECTION, FilamentAdjustment.Kind.RETIRE):
        raise InvalidFilamentAdjustment("Adjustment kind must be correction or retire.")
    reason = (reason or "").strip()
    if not reason:
        raise InvalidFilamentAdjustment("A reason is required.")
    value = coerce_grams(grams)
    if value == 0:
        raise InvalidFilamentAdjustment("Adjustment grams cannot be zero.")
    if kind == FilamentAdjustment.Kind.RETIRE and value > 0:
        raise InvalidFilamentAdjustment("Retire adjustments must remove grams.")

    with transaction.atomic():
        spool = FilamentSpool.objects.select_for_update().select_related("makerspace").get(pk=spool_id)
        remaining_before = spool.remaining_weight_grams
        remaining_after = remaining_before + value
        if remaining_after < 0:
            raise InvalidFilamentAdjustment("Adjustment would make remaining weight negative.")
        if remaining_after > spool.initial_weight_grams:
            raise InvalidFilamentAdjustment("Adjustment would exceed the spool initial weight.")

        remaining_decreased = remaining_after < remaining_before
        spool.remaining_weight_grams = remaining_after
        update_fields = ["remaining_weight_grams", "updated_at"]
        if kind == FilamentAdjustment.Kind.RETIRE and remaining_after == 0 and spool.is_active:
            spool.is_active = False
            update_fields.append("is_active")
        spool.save(update_fields=update_fields)

        adjustment = record_adjustment(
            actor=actor,
            spool=spool,
            kind=kind,
            grams=value,
            reason=reason,
        )
        audit.record(
            actor,
            "print.spool_adjusted",
            makerspace=spool.makerspace,
            target=spool,
            meta={
                "spool_id": spool.id,
                "adjustment_id": adjustment.id,
                "kind": kind,
                "grams": str(value),
                "remaining_before": str(remaining_before),
                "remaining_after": str(spool.remaining_weight_grams),
                "reason": reason,
            },
        )
        if remaining_decreased:
            from apps.printing.low_stock import maybe_flag_low_stock

            maybe_flag_low_stock(actor, spool)
        return spool, adjustment


def coerce_grams(value):
    try:
        grams = Decimal(str(value if value is not None else 0))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidFilamentAdjustment("Adjustment grams must be a valid decimal value.") from exc
    if not grams.is_finite():
        raise InvalidFilamentAdjustment("Adjustment grams must be finite.")
    return grams.quantize(Decimal("0.01"))
