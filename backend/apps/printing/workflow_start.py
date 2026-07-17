"""Validation and assignment helpers for starting print jobs."""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist

from apps.printing.models import FilamentSpool, PrintPrinter, PrintRequest
from apps.printing.spool_reservations import SpoolReservationError, reserve_filament
from apps.printing.workflow_errors import InvalidTransition, PrintStartValidationError


def coerce_filament_grams(grams):
    try:
        value = Decimal(str(grams))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidTransition("Actual filament grams must be a valid decimal value.") from exc
    if not value.is_finite() or value < 0:
        raise InvalidTransition(
            "Actual filament grams must be a finite decimal value greater than or equal to 0."
        )
    return value.quantize(Decimal("0.01"))


def coerce_price(price):
    try:
        value = Decimal(str(price if price is not None else 0))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidTransition("Price must be a valid decimal value.") from exc
    if not value.is_finite() or value < 0:
        raise InvalidTransition(
            "Price must be a finite decimal value greater than or equal to 0."
        )
    return value


def _positive_filament_grams(grams):
    value = coerce_filament_grams(grams)
    if value <= 0:
        raise PrintStartValidationError("Planned filament grams must be greater than 0.")
    return value


def _estimated_minutes(minutes):
    try:
        value = int(minutes)
    except (TypeError, ValueError) as exc:
        raise PrintStartValidationError("Estimated minutes must be a whole number.") from exc
    if value <= 0:
        raise PrintStartValidationError("Estimated minutes must be greater than 0.")
    return value


def assign_print_job(
    print_request, *, actor, printer_id, filament_spool_id,
    estimated_minutes, estimated_filament_grams,
):
    if printer_id is None:
        raise PrintStartValidationError("Printer is required to start a print.")
    if filament_spool_id is None:
        raise PrintStartValidationError("Filament spool is required to start a print.")
    if estimated_minutes is None:
        raise PrintStartValidationError("Estimated minutes are required to start a print.")
    if estimated_filament_grams is None:
        raise PrintStartValidationError("Planned filament grams are required to start a print.")
    estimated_minutes = _estimated_minutes(estimated_minutes)
    estimated_filament_grams = _positive_filament_grams(estimated_filament_grams)

    try:
        printer = PrintPrinter.objects.select_for_update().get(pk=printer_id)
    except ObjectDoesNotExist as exc:
        raise PrintStartValidationError("Printer was not found.") from exc
    if printer.makerspace_id != print_request.bucket.makerspace_id:
        raise PrintStartValidationError("Printer must belong to the request makerspace.")
    if not printer.is_active or printer.status != PrintPrinter.Status.ACTIVE:
        raise PrintStartValidationError("Printer is not available for printing.")
    if printer.print_requests.filter(status=PrintRequest.Status.PRINTING).exists():
        raise InvalidTransition("Printer already has an active print job.")

    try:
        spool = FilamentSpool.objects.select_for_update().get(pk=filament_spool_id)
    except ObjectDoesNotExist as exc:
        raise PrintStartValidationError("Filament spool was not found.") from exc
    if spool.makerspace_id != print_request.bucket.makerspace_id:
        raise PrintStartValidationError("Filament spool must belong to the request makerspace.")
    if spool.printer_id not in (None, printer.id):
        raise PrintStartValidationError("Filament spool is assigned to a different printer.")
    if not spool.is_active:
        raise PrintStartValidationError("Filament spool is not active.")

    print_request.printer = printer
    print_request.filament_spool = spool
    print_request.estimated_minutes = estimated_minutes
    print_request.estimated_filament_grams = estimated_filament_grams
    print_request.run_printer_name = printer.name
    print_request.run_printer_model = printer.model
    print_request.run_spool_label = _spool_label(spool)
    print_request.run_spool_material = spool.material
    print_request.run_spool_color = spool.color
    print_request.run_estimated_minutes = estimated_minutes
    print_request.run_planned_filament_grams = estimated_filament_grams
    if estimated_filament_grams > spool.remaining_weight_grams:
        raise PrintStartValidationError("Estimated filament exceeds remaining spool weight.")
    try:
        reserve_filament(actor, print_request)
    except SpoolReservationError as exc:
        raise PrintStartValidationError(str(exc)) from exc


def _spool_label(spool):
    parts = [spool.brand, spool.material, spool.color]
    return " ".join(part.strip() for part in parts if part and part.strip()) or spool.material
