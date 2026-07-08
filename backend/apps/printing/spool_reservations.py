from decimal import Decimal

from apps.audit import services as audit
from apps.printing.models import FilamentAdjustment, FilamentSpool
from apps.printing.services_filament_ledger import record_adjustment


class SpoolReservationError(Exception):
    pass


def reserve_filament(actor, print_request):
    grams = _decimal(print_request.estimated_filament_grams)
    if not print_request.filament_spool_id or grams <= 0:
        return

    spool = FilamentSpool.objects.select_for_update().get(
        pk=print_request.filament_spool_id,
    )
    if grams > spool.remaining_weight_grams:
        raise SpoolReservationError(
            "Estimated filament exceeds remaining spool weight."
        )

    remaining_before = spool.remaining_weight_grams
    spool.remaining_weight_grams -= grams
    spool.save(update_fields=["remaining_weight_grams", "updated_at"])
    record_adjustment(
        actor=actor,
        spool=spool,
        kind=FilamentAdjustment.Kind.RESERVE,
        grams=-grams,
        reason="Print start reservation",
        print_request=print_request,
    )
    print_request.filament_grams_reserved = grams
    print_request.filament_grams_used = Decimal("0.00")
    audit.record(
        actor,
        "print.spool_reserved",
        makerspace=print_request.bucket.makerspace,
        target=spool,
        meta={
            "spool_id": spool.id,
            "reserved_grams": str(grams),
            "remaining_before": str(remaining_before),
            "remaining_after": str(spool.remaining_weight_grams),
            "print_request_id": print_request.id,
        },
    )

    from apps.printing.low_stock import maybe_flag_low_stock

    maybe_flag_low_stock(actor, spool)


def reconcile_filament(actor, print_request, grams_used, *, reason):
    if not print_request.filament_spool_id:
        print_request.filament_grams_used = _decimal(grams_used)
        print_request.filament_grams_reserved = Decimal("0.00")
        print_request.save(
            update_fields=["filament_grams_used", "filament_grams_reserved"]
        )
        return

    used = _decimal(grams_used)
    reserved = _decimal(print_request.filament_grams_reserved)
    spool = FilamentSpool.objects.select_for_update().get(
        pk=print_request.filament_spool_id,
    )
    remaining_before = spool.remaining_weight_grams
    adjustment = used - reserved
    if adjustment > 0:
        if adjustment > spool.remaining_weight_grams:
            raise SpoolReservationError(
                "Final filament usage exceeds remaining spool weight."
            )
        spool.remaining_weight_grams -= adjustment
    elif adjustment < 0:
        spool.remaining_weight_grams = min(
            spool.initial_weight_grams,
            spool.remaining_weight_grams - adjustment,
        )
    remaining_decreased = spool.remaining_weight_grams < remaining_before
    spool.save(update_fields=["remaining_weight_grams", "updated_at"])
    record_adjustment(
        actor=actor,
        spool=spool,
        kind=FilamentAdjustment.Kind.RECONCILE,
        grams=-adjustment,
        reason=reason,
        print_request=print_request,
    )

    print_request.filament_grams_used = used
    print_request.filament_grams_reserved = Decimal("0.00")
    print_request.save(
        update_fields=["filament_grams_used", "filament_grams_reserved"]
    )
    audit.record(
        actor,
        "print.spool_reconciled",
        makerspace=print_request.bucket.makerspace,
        target=spool,
        meta={
            "spool_id": spool.id,
            "reserved_grams": str(reserved),
            "used_grams": str(used),
            "remaining_before": str(remaining_before),
            "remaining_after": str(spool.remaining_weight_grams),
            "print_request_id": print_request.id,
            "reason": reason,
        },
    )
    if remaining_decreased:
        from apps.printing.low_stock import maybe_flag_low_stock

        maybe_flag_low_stock(actor, spool)


def _decimal(value):
    return Decimal(value or 0).quantize(Decimal("0.01"))
