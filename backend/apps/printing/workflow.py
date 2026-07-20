from decimal import Decimal
import json

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.notifications.emit import emit_notification
from apps.printing.emails import notify_print_status
from apps.printing.models import PrintRequest
from apps.printing.spool_reservations import (
    SpoolReservationError,
    reconcile_filament,
)
from apps.printing.workflow_errors import InvalidTransition, PrintStartValidationError
from apps.printing.workflow_start import assign_print_job, coerce_filament_grams, coerce_price
from apps.machines.printing_cutover import kernel_is_authoritative


_ALLOWED = {
    PrintRequest.Status.PENDING: {PrintRequest.Status.ACCEPTED, PrintRequest.Status.REJECTED},
    PrintRequest.Status.ACCEPTED: {PrintRequest.Status.PRINTING},
    PrintRequest.Status.PRINTING: {PrintRequest.Status.COMPLETED, PrintRequest.Status.FAILED},
    PrintRequest.Status.COMPLETED: {PrintRequest.Status.COLLECTED},
}


def _kernel_request(legacy):
    """Resolve one legacy compatibility target without ever aggregating sides."""
    if isinstance(legacy, LegacyPrintRequestAdapter):
        return legacy._service_request
    from apps.machines.models import MachineServiceRequest
    try:
        return MachineServiceRequest.objects.get(legacy_print_request_id=legacy.pk)
    except MachineServiceRequest.DoesNotExist as exc:
        raise InvalidTransition("Print request has not been reconciled to the machine kernel.") from exc


def _kernel_enabled(legacy):
    if isinstance(legacy, LegacyPrintRequestAdapter):
        return True
    return kernel_is_authoritative(legacy.bucket.makerspace)


def _legacy_status(status):
    return PrintRequest.Status.PRINTING if status == "in_progress" else status


class _KernelFiles:
    """Small related-manager facade for the legacy response serializer."""

    def __init__(self, service_request):
        self.service_request = service_request

    def all(self):
        return self.service_request.files.all()


class LegacyPrintRequestAdapter:
    """Expose a kernel mutation through the established managed-print contract.

    The legacy print row remains immutable after cutover; this is a response
    projection only, not a reverse synchronisation path.
    """

    def __init__(self, service_request, legacy=None, *, identifier=None):
        from apps.printing.models import PrintBucket

        self._service_request = service_request
        source_legacy = legacy._legacy if isinstance(legacy, LegacyPrintRequestAdapter) else legacy
        self._legacy = source_legacy
        # Kernel requests live in a distinct, negative namespace.  A retained
        # legacy PK can otherwise collide with an unrelated kernel request.
        self.id = -service_request.pk if identifier is None else identifier
        self.bucket = legacy.bucket if legacy is not None else PrintBucket.objects.get(
            pk=service_request.queue.legacy_print_bucket_id,
        )
        self.requester = service_request.requester
        self.requester_name = service_request.requester_name
        self.contact_email = service_request.contact_email
        self.contact_phone = service_request.contact_phone
        self.title = service_request.title
        self.description = service_request.description
        self.source_link = service_request.source_link
        payload = service_request.capability_payload or {}
        self.material = payload.get("requested_material", "")
        self.color = payload.get("requested_color", "")
        self.quantity = payload.get("quantity", 1)
        self.project_brief = payload.get("project_brief", "")
        settings = payload.get("preferred_settings", "")
        self.preferred_settings = json.dumps(settings, sort_keys=True) if isinstance(settings, dict) else settings
        self.model_file = ""
        self.estimate_screenshot = ""
        self.preview_screenshot = ""
        self.status = _legacy_status(service_request.status)
        self.reason = service_request.reason
        self.handled_by = service_request.handled_by
        self.accepted_by = service_request.accepted_by
        self.accepted_at = service_request.accepted_at
        self.started_at = service_request.started_at
        self.completed_at = service_request.completed_at
        self.collected_at = service_request.collected_at
        self.collected_by = service_request.collected_by
        self.created_at = service_request.created_at
        self.updated_at = service_request.updated_at
        self.estimated_minutes = service_request.estimated_minutes
        self.estimated_filament_grams = service_request.planned_grams
        self.filament_grams_reserved = service_request.reserved_grams
        self.filament_grams_used = service_request.actual_consumed_grams
        self.run_printer_name = service_request.run_machine_name
        self.run_printer_model = service_request.run_machine_model
        self.run_spool_label = service_request.run_consumable_label
        self.run_spool_material = service_request.run_consumable_material
        self.run_spool_color = service_request.run_consumable_color
        self.run_estimated_minutes = service_request.run_estimated_minutes
        self.run_planned_filament_grams = service_request.run_planned_grams
        self.price = service_request.payment_amount or Decimal("0.00")
        self.payment_status = service_request.payment_status
        self.paid_at = service_request.paid_at
        self.files = _KernelFiles(service_request)
        self.requested_filament_spool = None
        # A kernel start owns the authoritative assignment.  Project its
        # reconciled legacy identities for the compatibility serializer instead
        # of falling back to the frozen pre-cutover request values.
        self.printer = None
        self.filament_spool = None
        if service_request.assigned_machine_id:
            from apps.printing.models import PrintPrinter
            self.printer = PrintPrinter.objects.filter(
                pk=service_request.assigned_machine.legacy_print_printer_id,
            ).first()
        if service_request.run_consumable_pool_id:
            from apps.printing.models import FilamentSpool
            self.filament_spool = FilamentSpool.objects.filter(
                pk=service_request.run_consumable_pool.legacy_filament_spool_id,
            ).first()
        requested_pool_id = payload.get("requested_consumable_pool")
        if requested_pool_id:
            from apps.machines.models import MachineConsumablePool
            from apps.printing.models import FilamentSpool
            legacy_pool = MachineConsumablePool.objects.filter(pk=requested_pool_id).first()
            if legacy_pool is not None:
                self.requested_filament_spool = FilamentSpool.objects.filter(
                    pk=legacy_pool.legacy_filament_spool_id,
                ).first()
        self.reprint_of = service_request.reprint_of if service_request.reprint_of_id else None
        self.reprint_of_id = -service_request.reprint_of_id if service_request.reprint_of_id else None
        self.public_token = service_request.public_token

    def __getattr__(self, name):
        if self._legacy is None:
            raise AttributeError(name)
        return getattr(self._legacy, name)


def legacy_compatible_response(service_request, legacy=None, *, identifier=None):
    return LegacyPrintRequestAdapter(service_request, legacy, identifier=identifier)


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
            assign_print_job(
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
            locked.price = coerce_price(price)
            extra_update_fields.extend(["accepted_by", "price"])
            # The manager can set/edit the planned filament at accept. `is not None`
            # (not truthiness) so an explicit 0 updates while an omitted field
            # preserves the requester's submitted estimate.
            if estimated_filament_grams is not None:
                locked.estimated_filament_grams = coerce_filament_grams(
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
        notify_print_status(locked, event)
        return locked


def _reconcile_spool(actor, locked, grams, reason):
    try:
        reconcile_filament(actor, locked, grams, reason=reason)
    except SpoolReservationError as exc:
        raise InvalidTransition(str(exc)) from exc


def accept(print_request, actor, *, price=0, estimated_filament_grams=None):
    if _kernel_enabled(print_request):
        from apps.machines import service_workflow
        result = service_workflow.accept(
            _kernel_request(print_request), actor, estimated_minutes=None,
            planned_grams=estimated_filament_grams, payment_amount=price,
        )
        return legacy_compatible_response(result, print_request)
    return _transition(
        print_request,
        actor,
        PrintRequest.Status.ACCEPTED,
        "accepted",
        price=price,
        estimated_filament_grams=estimated_filament_grams,
    )

def reject(print_request, actor, reason):
    if _kernel_enabled(print_request):
        from apps.machines import service_workflow
        result = service_workflow.reject(_kernel_request(print_request), actor, reason=reason)
        return legacy_compatible_response(result, print_request)
    return _transition(print_request, actor, PrintRequest.Status.REJECTED, "rejected", reason=reason)

def start(
    print_request, actor, *, printer_id=None, filament_spool_id=None,
    estimated_minutes=None, estimated_filament_grams=None,
):
    if _kernel_enabled(print_request):
        from apps.machines import service_workflow
        from apps.machines.models import Machine, MachineConsumablePool
        machine = Machine.objects.filter(
            legacy_print_printer_id=printer_id, makerspace=print_request.bucket.makerspace,
        ).first()
        if machine is None:
            raise PrintStartValidationError("Invalid printer for this print request.")
        pool = MachineConsumablePool.objects.filter(
            legacy_filament_spool_id=filament_spool_id,
            makerspace=print_request.bucket.makerspace,
        ).first()
        if pool is None:
            raise PrintStartValidationError("Invalid filament spool for this print request.")
        target = _kernel_request(print_request)
        result = service_workflow.start(target, actor, machine_id=machine.pk,
                                        consumable_pool_id=pool.pk, estimated_minutes=estimated_minutes,
                                        planned_grams=(target.planned_grams if estimated_filament_grams is None else estimated_filament_grams))
        return legacy_compatible_response(result, print_request)
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
    if _kernel_enabled(print_request):
        from apps.machines import service_workflow
        target = _kernel_request(print_request)
        result = service_workflow.complete(target, actor, actual_minutes=target.estimated_minutes,
                                           consumptions=[], actual_grams=actual_filament_grams)
        return legacy_compatible_response(result, print_request)
    if actual_filament_grams is not None:
        actual_filament_grams = coerce_filament_grams(actual_filament_grams)
    return _transition(
        print_request,
        actor,
        PrintRequest.Status.COMPLETED,
        "completed",
        actual_filament_grams=actual_filament_grams,
    )

def fail(print_request, actor, reason, percent_complete=0):
    if _kernel_enabled(print_request):
        from apps.machines import service_workflow
        target = _kernel_request(print_request)
        result = service_workflow.fail(target, actor, reason=reason, percent_complete=percent_complete,
                                       actual_minutes=target.estimated_minutes, consumptions=[])
        return legacy_compatible_response(result, print_request)
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
            body=f"Print request #{result.pk} failed.",
        )
    except Exception:
        pass
    return result

def mark_collected(print_request, actor):
    if _kernel_enabled(print_request):
        from apps.machines import service_workflow
        result = service_workflow.collect(_kernel_request(print_request), actor)
        return legacy_compatible_response(result, print_request)
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
        notify_print_status(locked, "collected")
        return locked


def reprint(failed_request, actor):
    if _kernel_enabled(failed_request):
        from apps.machines import service_workflow
        result = service_workflow.create_reprint(_kernel_request(failed_request), actor)
        # This is a new kernel request, not a mutation of the failed source.
        # Return its identifier so clients do not target the failed request.
        return legacy_compatible_response(result, failed_request)
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
        notify_print_status(clone, "reprinted")
        return clone




