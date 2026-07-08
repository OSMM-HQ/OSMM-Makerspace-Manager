from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from apps.audit import services as audit
from apps.notifications.emit import emit_notification
from apps.printing.emails import queue_print_email, queue_staff_print_email
from apps.printing.models import FilamentSpool, PrintPrinter, PrintRequest
from apps.printing.spool_reservations import (
    SpoolReservationError,
    reconcile_filament,
    reserve_filament,
)


class InvalidTransition(Exception):
    pass


class PrintStartValidationError(InvalidTransition):
    pass


_ALLOWED = {
    PrintRequest.Status.PENDING: {PrintRequest.Status.ACCEPTED, PrintRequest.Status.REJECTED},
    PrintRequest.Status.ACCEPTED: {PrintRequest.Status.PRINTING},
    PrintRequest.Status.PRINTING: {PrintRequest.Status.COMPLETED, PrintRequest.Status.FAILED},
    PrintRequest.Status.COMPLETED: {PrintRequest.Status.COLLECTED},
}


def _locked_request(pk, *related):
    qs = PrintRequest.objects.select_for_update()
    if related:
        qs = qs.select_related(*related)
    return qs.get(pk=pk)


def _transition(
    print_request, actor, status, event, reason="", printer_id=None,
    filament_spool_id=None, estimated_minutes=None,
    estimated_filament_grams=None, actual_filament_grams=None,
    percent_complete=0, price=0,
):
    with transaction.atomic():
        locked = _locked_request(print_request.pk, "bucket__makerspace", "requester")
        if status not in _ALLOWED.get(locked.status, set()):
            raise InvalidTransition(
                f"Cannot transition print request from {locked.status} to {status}."
            )

        extra_update_fields = []
        now = timezone.now()
        if status == PrintRequest.Status.PRINTING:
            _assign_print_job(
                locked,
                actor=actor,
                printer_id=printer_id,
                filament_spool_id=filament_spool_id,
                estimated_minutes=estimated_minutes,
                estimated_filament_grams=estimated_filament_grams,
            )
            locked.started_at = now
            extra_update_fields.extend(
                ["printer", "filament_spool", "estimated_minutes",
                 "estimated_filament_grams", "filament_grams_reserved",
                 "filament_grams_used", "started_at", "run_printer_name",
                 "run_printer_model", "run_spool_label", "run_spool_material",
                 "run_spool_color", "run_estimated_minutes",
                 "run_planned_filament_grams"]
            )

        locked.status = status
        locked.handled_by = actor
        if status == PrintRequest.Status.ACCEPTED:
            locked.accepted_at = now
            locked.accepted_by = actor
            locked.price = _coerce_price(price)
            extra_update_fields.extend(["accepted_by", "price"])
            # The manager can set/edit the planned filament at accept. `is not None`
            # (not truthiness) so an explicit 0 updates while an omitted field
            # preserves the requester's submitted estimate.
            if estimated_filament_grams is not None:
                locked.estimated_filament_grams = _coerce_filament_grams(
                    estimated_filament_grams
                )
                extra_update_fields.append("estimated_filament_grams")
        if status == PrintRequest.Status.COMPLETED:
            locked.completed_at = now
            locked.payment_status = (
                PrintRequest.PaymentStatus.PENDING
                if locked.price and locked.price > 0
                else PrintRequest.PaymentStatus.NONE
            )
            extra_update_fields.append("payment_status")
        if status in (PrintRequest.Status.REJECTED, PrintRequest.Status.FAILED):
            locked.reason = reason
        if status == PrintRequest.Status.FAILED:
            # Persist how far the print got + when it failed, so failed jobs can
            # contribute partial time to printer-hour reports (failed rows have no
            # completed_at, so failed_at is what date-window queries filter on).
            locked.fail_percent_complete = max(0, min(100, int(percent_complete or 0)))
            locked.failed_at = now
            extra_update_fields.extend(["fail_percent_complete", "failed_at"])

        locked.save(
            update_fields=[
                "status", "handled_by", "accepted_at", "started_at",
                "completed_at", "reason", "updated_at",
            ]
            + extra_update_fields
        )
        audit.record(actor, f"print.{event}", makerspace=locked.bucket.makerspace, target=locked)
        if status == PrintRequest.Status.COMPLETED:
            completion_grams = (
                locked.estimated_filament_grams
                if actual_filament_grams is None
                else actual_filament_grams
            )
            if completion_grams is not None and (
                actual_filament_grams is not None
                or locked.filament_grams_reserved > 0
                or (locked.filament_spool_id and completion_grams > 0)
            ):
                _reconcile_spool(actor, locked, completion_grams, "completed")
        elif (
            status == PrintRequest.Status.FAILED
            and locked.filament_spool_id
            and locked.estimated_filament_grams
            and locked.estimated_filament_grams > 0
        ):
            partial = (
                locked.estimated_filament_grams
                * Decimal(percent_complete)
                / Decimal(100)
            ).quantize(Decimal("0.01"))
            if partial > 0:
                _reconcile_spool(actor, locked, partial, "failed_partial")
            else:
                _reconcile_spool(actor, locked, Decimal("0.00"), "failed_partial")
        if event in {"accepted", "started", "rejected", "completed"}:
            queue_print_email(event, locked.pk)
        if event in {"accepted", "started", "rejected", "completed", "failed"}:
            queue_staff_print_email(event, locked.pk)
        return locked


def _reconcile_spool(actor, locked, grams, reason):
    try:
        reconcile_filament(actor, locked, grams, reason=reason)
    except SpoolReservationError as exc:
        raise InvalidTransition(str(exc)) from exc


def _coerce_filament_grams(grams):
    try:
        value = Decimal(str(grams))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidTransition("Actual filament grams must be a valid decimal value.") from exc
    if not value.is_finite() or value < 0:
        raise InvalidTransition(
            "Actual filament grams must be a finite decimal value greater than or equal to 0."
        )
    return value.quantize(Decimal("0.01"))



def _coerce_positive_filament_grams(grams):
    value = _coerce_filament_grams(grams)
    if value <= 0:
        raise PrintStartValidationError("Planned filament grams must be greater than 0.")
    return value


def _coerce_estimated_minutes(minutes):
    try:
        value = int(minutes)
    except (TypeError, ValueError) as exc:
        raise PrintStartValidationError("Estimated minutes must be a whole number.") from exc
    if value <= 0:
        raise PrintStartValidationError("Estimated minutes must be greater than 0.")
    return value
def _coerce_price(price):
    try:
        value = Decimal(str(price if price is not None else 0))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidTransition("Price must be a valid decimal value.") from exc
    if not value.is_finite() or value < 0:
        raise InvalidTransition("Price must be a finite decimal value greater than or equal to 0.")
    return value


def _assign_print_job(
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

    estimated_minutes = _coerce_estimated_minutes(estimated_minutes)
    estimated_filament_grams = _coerce_positive_filament_grams(estimated_filament_grams)

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

def accept(print_request, actor, *, price=0, estimated_filament_grams=None):
    return _transition(
        print_request,
        actor,
        PrintRequest.Status.ACCEPTED,
        "accepted",
        price=price,
        estimated_filament_grams=estimated_filament_grams,
    )

def reject(print_request, actor, reason):
    return _transition(print_request, actor, PrintRequest.Status.REJECTED, "rejected", reason=reason)

def start(
    print_request, actor, *, printer_id=None, filament_spool_id=None,
    estimated_minutes=None, estimated_filament_grams=None,
):
    return _transition(
        print_request,
        actor,
        PrintRequest.Status.PRINTING,
        "started",
        printer_id=printer_id,
        filament_spool_id=filament_spool_id,
        estimated_minutes=estimated_minutes,
        estimated_filament_grams=estimated_filament_grams,
    )

def complete(print_request, actor, *, actual_filament_grams=None):
    if actual_filament_grams is not None:
        actual_filament_grams = _coerce_filament_grams(actual_filament_grams)
    return _transition(
        print_request,
        actor,
        PrintRequest.Status.COMPLETED,
        "completed",
        actual_filament_grams=actual_filament_grams,
    )

def fail(print_request, actor, reason, percent_complete=0):
    result = _transition(
        print_request, actor, PrintRequest.Status.FAILED, "failed",
        reason=reason, percent_complete=percent_complete,
    )
    try:
        emit_notification(
            result.bucket.makerspace,
            level="warning",
            event="print.failed",
            title="Print job failed",
            body=str(reason or "")[:500],
        )
    except Exception:
        pass
    return result

def mark_collected(print_request, actor):
    with transaction.atomic():
        locked = _locked_request(print_request.pk, "bucket__makerspace")
        if PrintRequest.Status.COLLECTED not in _ALLOWED.get(locked.status, set()):
            raise InvalidTransition(
                f"Cannot transition print request from {locked.status} to collected."
            )

        now = timezone.now()
        locked.status = PrintRequest.Status.COLLECTED
        locked.collected_at = now
        locked.collected_by = actor
        locked.handled_by = actor
        update_fields = ["status", "collected_at", "collected_by", "handled_by", "updated_at"]
        if locked.price and locked.price > 0:
            locked.payment_status = PrintRequest.PaymentStatus.PAID
            locked.paid_at = now
            update_fields.extend(["payment_status", "paid_at"])

        locked.save(update_fields=update_fields)
        audit.record(
            actor,
            "print.collected",
            makerspace=locked.bucket.makerspace,
            target=locked,
            meta={"price": str(locked.price), "payment_status": locked.payment_status},
        )
        queue_staff_print_email("collected", locked.pk)
        return locked


def reprint(failed_request, actor):
    with transaction.atomic():
        locked = _locked_request(failed_request.pk, "bucket__makerspace")
        if locked.status != PrintRequest.Status.FAILED:
            raise InvalidTransition("Only failed print requests can be reprinted.")
        # Reprint clones own no files, so anchor retries to the file-owning root.
        root = locked.reprint_of if locked.reprint_of_id else locked
        clone = PrintRequest.objects.create(
            bucket=locked.bucket,
            requester=locked.requester,
            requester_name=locked.requester_name,
            title=locked.title,
            description=locked.description,
            material=locked.material,
            color=locked.color,
            quantity=locked.quantity,
            source_link=locked.source_link,
            project_brief=locked.project_brief,
            preferred_settings=locked.preferred_settings,
            contact_email=locked.contact_email,
            contact_phone=locked.contact_phone,
            requested_filament_spool=locked.requested_filament_spool,
            estimated_minutes=locked.estimated_minutes,
            estimated_filament_grams=locked.estimated_filament_grams,
            price=locked.price,
            model_file=locked.model_file,
            estimate_screenshot=locked.estimate_screenshot,
            preview_screenshot=locked.preview_screenshot,
            status=PrintRequest.Status.ACCEPTED,
            handled_by=actor,
            accepted_by=actor,
            accepted_at=timezone.now(),
            reprint_of=root,
        )
        audit.record(
            actor,
            "print.reprinted",
            makerspace=locked.bucket.makerspace,
            target=clone,
            meta={
                "original_id": root.id, "reprinted_from_id": locked.id,
                "reprint_id": clone.id,
            },
        )
        queue_staff_print_email("reprinted", clone.pk)
        return clone




