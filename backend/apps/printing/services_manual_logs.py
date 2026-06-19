from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from apps.audit import services as audit
from apps.printing.models import FilamentSpool, ManualPrintLog, PrintPrinter
from apps.printing.workflow import InvalidTransition


def log_manual_print(
    actor,
    makerspace,
    printer,
    filament_spool,
    grams_used,
    title,
    note,
    duration_minutes=0,
):
    with transaction.atomic():
        try:
            printer = PrintPrinter.objects.select_for_update().get(pk=printer.pk)
        except ObjectDoesNotExist as exc:
            raise InvalidTransition("Printer was not found.") from exc
        if printer.makerspace_id != makerspace.id:
            raise InvalidTransition("Printer must belong to this makerspace.")
        if not printer.is_active or printer.status != PrintPrinter.Status.ACTIVE:
            raise InvalidTransition("Printer is not active.")
        if grams_used <= 0:
            raise InvalidTransition("Filament used must be greater than zero.")
        if duration_minutes is None or duration_minutes < 0:
            raise InvalidTransition("Print time minutes cannot be negative.")
        spool = FilamentSpool.objects.select_for_update().get(pk=filament_spool.pk)
        if spool.makerspace_id != makerspace.id:
            raise InvalidTransition("Filament spool must belong to this makerspace.")
        if spool.printer_id not in (None, printer.id):
            raise InvalidTransition("Filament spool is assigned to a different printer.")
        if not spool.is_active:
            raise InvalidTransition("Filament spool is not active.")
        # Mirror the regular print-start invariant: never record usage that
        # overdraws the tracked spool, or manual-log/printer grams would exceed
        # the spool-derived filament totals. The operator should correct the
        # spool's remaining weight first if it is inaccurate.
        if grams_used > spool.remaining_weight_grams:
            raise InvalidTransition("Filament used exceeds remaining spool weight.")

        remaining_before = spool.remaining_weight_grams
        spool.remaining_weight_grams = max(remaining_before - grams_used, Decimal("0"))
        spool.save(update_fields=["remaining_weight_grams", "updated_at"])
        log = ManualPrintLog.objects.create(
            makerspace=makerspace,
            printer=printer,
            filament_spool=spool,
            grams_used=grams_used,
            duration_minutes=duration_minutes or 0,
            title=title,
            note=note,
            logged_by=actor,
        )
        audit.record(
            actor,
            "print.manual_logged",
            makerspace=makerspace,
            target=log,
            meta={
                "printer_id": printer.id,
                "spool_id": spool.id,
                "grams_used": str(grams_used),
                "remaining_before": str(remaining_before),
                "remaining_after": str(spool.remaining_weight_grams),
            },
        )
        return log
