"""B4 deterministic import, reconciliation, and authority boundary.

This module intentionally has no reverse writer.  Legacy rows are provenance
evidence; after ``flip_authority`` every new print mutation is kernel-only and
repairs add kernel records or repair rows.
"""

from collections import Counter
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.machines.models import (
    Machine, MachineConsumableAdjustment, MachineConsumablePool,
    MachineServiceRequest, MachineUsageEntry, PrintingCutoverRepair,
    PrintingCutoverState, ServiceQueue, ServiceRequestFile,
)
from apps.machines.printer_capabilities import PRINTER_SLUG


class CutoverMismatch(RuntimeError):
    """Raised after durable repair evidence is written for a failed gate."""


def kernel_is_authoritative(makerspace):
    return PrintingCutoverState.objects.filter(
        makerspace=makerspace, kernel_authoritative_at__isnull=False
    ).exists()


def _repair(makerspace, kind, model, legacy_id=None, **detail):
    row, _ = PrintingCutoverRepair.objects.get_or_create(
        makerspace=makerspace, kind=kind, legacy_model=model, legacy_id=legacy_id,
        defaults={"detail": detail},
    )
    return row


def _printer_type():
    from apps.machines.models import MachineType
    return MachineType.objects.get(makerspace__isnull=True, slug=PRINTER_SLUG)


def _timestamp(model, pk, created, updated=None):
    values = {"created_at": created}
    if updated is not None:
        values["updated_at"] = updated
    model.objects.filter(pk=pk).update(**values)


def _printer(legacy, printer_type):
    machine = Machine.objects.filter(legacy_print_printer_id=legacy.pk).first()
    if machine:
        return machine
    machine = Machine.objects.filter(linked_print_printer_id=legacy.pk).first()
    if machine and (machine.makerspace_id != legacy.makerspace_id or machine.machine_type_id != printer_type.id):
        _repair(legacy.makerspace, "invalid_source", "printing.PrintPrinter", legacy.pk, reason="linked machine does not match makerspace/type")
        raise CutoverMismatch("Printer bridge mismatch")
    if machine is None:
        status = {"maintenance": Machine.Status.MAINTENANCE, "offline": Machine.Status.OFFLINE}.get(legacy.status, Machine.Status.IDLE)
        machine = Machine.objects.create(
            makerspace=legacy.makerspace, machine_type=printer_type, name=legacy.name,
            notes=legacy.notes, image_key=legacy.image_key, is_active=legacy.is_active,
            status=status, type_payload={"model": legacy.model or "Legacy printer"},
        )
    machine.legacy_print_printer_id = legacy.pk
    machine.save(update_fields=["legacy_print_printer_id"])
    _timestamp(Machine, machine.pk, legacy.created_at, legacy.updated_at)
    return machine


def _queue(legacy, printer_type):
    queue, created = ServiceQueue.objects.get_or_create(
        legacy_print_bucket_id=legacy.pk,
        defaults={"makerspace": legacy.makerspace, "machine_type": printer_type, "name": legacy.name,
                  "description": legacy.description, "is_active": legacy.is_active},
    )
    if not created and queue.makerspace_id != legacy.makerspace_id:
        _repair(legacy.makerspace, "collision", "printing.PrintBucket", legacy.pk, reason="provenance belongs to another makerspace")
        raise CutoverMismatch("Queue provenance collision")
    _timestamp(ServiceQueue, queue.pk, legacy.created_at, legacy.updated_at)
    return queue


def _pool(legacy, machine_by_legacy):
    pool, created = MachineConsumablePool.objects.get_or_create(
        legacy_filament_spool_id=legacy.pk,
        defaults={"makerspace": legacy.makerspace, "machine": machine_by_legacy.get(legacy.printer_id),
                  "material": legacy.material, "color": legacy.color, "brand": legacy.brand,
                  "lot_code": legacy.lot_code, "initial_grams": legacy.initial_weight_grams,
                  "remaining_grams": legacy.initial_weight_grams, "is_active": legacy.is_active,
                  "opened_at": legacy.opened_at},
    )
    if not created and pool.makerspace_id != legacy.makerspace_id:
        _repair(legacy.makerspace, "collision", "printing.FilamentSpool", legacy.pk, reason="provenance belongs to another makerspace")
        raise CutoverMismatch("Pool provenance collision")
    _timestamp(MachineConsumablePool, pool.pk, legacy.created_at, legacy.updated_at)
    return pool


def _request(legacy, queue_by_legacy, machine_by_legacy, pool_by_legacy):
    status = "in_progress" if legacy.status == "printing" else legacy.status
    request, created = MachineServiceRequest.objects.get_or_create(
        legacy_print_request_id=legacy.pk,
        defaults={
            "queue": queue_by_legacy[legacy.bucket_id], "makerspace": legacy.bucket.makerspace,
            "requester": legacy.requester, "title": legacy.title, "description": legacy.description,
            "source_link": legacy.source_link, "status": status, "reason": legacy.reason,
            "assigned_machine": machine_by_legacy.get(legacy.printer_id), "handled_by": legacy.handled_by,
            "accepted_by": legacy.accepted_by, "accepted_at": legacy.accepted_at, "started_at": legacy.started_at,
            "completed_at": legacy.completed_at, "failed_at": legacy.failed_at, "collected_by": legacy.collected_by,
            "collected_at": legacy.collected_at, "estimated_minutes": legacy.estimated_minutes,
            "actual_minutes": legacy.estimated_minutes if legacy.status in ("completed", "collected") else 0,
            "fail_percent_complete": legacy.fail_percent_complete, "planned_grams": legacy.estimated_filament_grams,
            "reserved_grams": legacy.filament_grams_reserved, "actual_consumed_grams": legacy.filament_grams_used,
            "run_consumable_pool": pool_by_legacy.get(legacy.filament_spool_id), "payment_amount": legacy.price,
            "payment_status": legacy.payment_status, "paid_at": legacy.paid_at, "public_token": legacy.public_token,
            "run_machine_name": legacy.run_printer_name, "run_machine_model": legacy.run_printer_model,
            "run_consumable_label": legacy.run_spool_label, "run_consumable_material": legacy.run_spool_material,
            "run_consumable_color": legacy.run_spool_color, "run_estimated_minutes": legacy.run_estimated_minutes or 0,
            "run_planned_grams": legacy.run_planned_filament_grams or 0,
            "capability_payload": {"requested_material": legacy.material, "requested_color": legacy.color,
                                   "quantity": legacy.quantity, "project_brief": legacy.project_brief,
                                   **({"requested_consumable_pool": pool_by_legacy[legacy.requested_filament_spool_id].pk}
                                      if legacy.requested_filament_spool_id in pool_by_legacy else {})},
            "requester_name": legacy.requester_name, "contact_email": legacy.contact_email, "contact_phone": legacy.contact_phone,
        },
    )
    if not created and request.makerspace_id != legacy.makerspace_id:
        _repair(legacy.makerspace, "collision", "printing.PrintRequest", legacy.pk, reason="provenance belongs to another makerspace")
        raise CutoverMismatch("Request provenance collision")
    _timestamp(MachineServiceRequest, request.pk, legacy.created_at, legacy.updated_at)
    return request


def backfill(makerspace, *, actor=None):
    """Idempotently import one tenant.  Invalid source data stops the cutover."""
    from apps.printing.models import FilamentSpool, PrintBucket, PrintPrinter, PrintRequest
    try:
        with transaction.atomic():
            printer_type = _printer_type()
            machines = {row.pk: _printer(row, printer_type) for row in PrintPrinter.objects.filter(makerspace=makerspace)}
            queues = {row.pk: _queue(row, printer_type) for row in PrintBucket.objects.filter(makerspace=makerspace)}
            pools = {row.pk: _pool(row, machines) for row in FilamentSpool.objects.filter(makerspace=makerspace)}
            _backfill_warranties(makerspace, machines)
            requests = {row.pk: _request(row, queues, machines, pools) for row in PrintRequest.objects.filter(bucket__makerspace=makerspace).select_related("bucket", "requester")}
            _backfill_reprints(makerspace, requests)
            _backfill_files(makerspace, requests)
            _backfill_manual_and_ledger(makerspace, machines, pools, requests)
            reconcile(makerspace)
            state, _ = PrintingCutoverState.objects.get_or_create(makerspace=makerspace)
            state.reconciled_at = timezone.now()
            state.save(update_fields=["reconciled_at", "updated_at"])
            audit.record(actor, "machine_printing.backfilled", makerspace=makerspace, target=state)
            return state
    except CutoverMismatch as exc:
        # The import transaction rolls back; this durable row is intentionally
        # written afterwards so operators have evidence for forward repair.
        _repair(makerspace, "mismatch", "machines.printing_cutover", None, error=str(exc))
        raise


def _backfill_warranties(makerspace, machines):
    from apps.warranty.models import Warranty
    for warranty in Warranty.objects.filter(makerspace=makerspace, printer__isnull=False):
        machine = machines.get(warranty.printer_id)
        if machine is None:
            _repair(makerspace, "warranty", "warranty.Warranty", warranty.pk, printer_id=warranty.printer_id)
            raise CutoverMismatch("Warranty printer has no kernel machine")
        # One SQL update changes both XOR hosts together; no transient invalid
        # warranty row is exposed and the legacy host remains untouched.
        Warranty.objects.filter(pk=warranty.pk).update(printer=None, machine=machine)


def _backfill_reprints(makerspace, requests):
    from apps.printing.models import PrintRequest
    for legacy in PrintRequest.objects.filter(bucket__makerspace=makerspace, reprint_of__isnull=False):
        child, root = requests[legacy.pk], requests.get(legacy.reprint_of_id)
        if root is None:
            _repair(makerspace, "invalid_source", "printing.PrintRequest", legacy.pk, reason="missing reprint root")
            raise CutoverMismatch("Missing reprint root")
        if child.reprint_of_id != root.pk:
            MachineServiceRequest.objects.filter(pk=child.pk).update(reprint_of=root)


def _backfill_files(makerspace, requests):
    from apps.printing.models import PrintRequest, PrintRequestFile
    for row in PrintRequestFile.objects.filter(makerspace=makerspace).select_related("print_request", "owner"):
        if not row.print_request_id:
            _repair(makerspace, "invalid_source", "printing.PrintRequestFile", row.pk, reason="unattached staged upload")
            continue
        request = requests.get(row.print_request_id)
        if request is None:
            _repair(makerspace, "invalid_source", "printing.PrintRequestFile", row.pk, reason="missing imported request")
            raise CutoverMismatch("Missing file request")
        duplicate = ServiceRequestFile.objects.filter(object_key=row.object_key).exclude(legacy_print_request_file_id=row.pk).first()
        if duplicate:
            _repair(makerspace, "collision", "printing.PrintRequestFile", row.pk, object_key=row.object_key, kernel_file_id=duplicate.pk)
            raise CutoverMismatch("Object key collision")
        target, _ = ServiceRequestFile.objects.get_or_create(
            legacy_print_request_file_id=row.pk,
            defaults={"service_request": request, "makerspace": makerspace, "machine": request.assigned_machine,
                      "kind": "model" if row.kind == "stl" else "screenshot", "object_key": row.object_key,
                      "content_type": row.content_type, "original_filename": row.original_filename,
                      "size_bytes": row.size_bytes, "owner_user_id": row.owner_id or 0,
                      "file_policy_name": "printer", "file_policy_version": 1, "attached_at": row.attached_at},
        )
        _timestamp(ServiceRequestFile, target.pk, row.created_at)
    # Historical FileFields are attachment evidence too; their original object
    # keys are retained without claiming a byte size the legacy DB never knew.
    for legacy in PrintRequest.objects.filter(bucket__makerspace=makerspace):
        request = requests[legacy.pk]
        root = requests.get(legacy.reprint_of_id, request)
        for field, kind in (("model_file", "model"), ("estimate_screenshot", "estimate"), ("preview_screenshot", "preview")):
            key = getattr(legacy, field).name
            if not key:
                continue
            existing = ServiceRequestFile.objects.filter(object_key=key).first()
            if existing and existing.service_request_id != root.pk:
                _repair(makerspace, "collision", "printing.PrintRequest", legacy.pk, object_key=key)
                raise CutoverMismatch("Historical object key collision")
            if not existing:
                ServiceRequestFile.objects.create(service_request=root, makerspace=makerspace, machine=root.assigned_machine,
                    kind=kind, object_key=key, owner_user_id=legacy.requester_id, file_policy_name="printer", attached_at=legacy.created_at)


def _backfill_manual_and_ledger(makerspace, machines, pools, requests):
    from apps.printing.models import FilamentAdjustment, ManualPrintLog
    manual = {}
    for row in ManualPrintLog.objects.filter(makerspace=makerspace).select_related("logged_by"):
        machine = machines.get(row.printer_id)
        if machine is None:
            _repair(makerspace, "invalid_source", "printing.ManualPrintLog", row.pk, reason="manual log has no printer machine")
            raise CutoverMismatch("Manual log missing machine")
        target, _ = MachineUsageEntry.objects.get_or_create(
            legacy_manual_print_log_id=row.pk,
            defaults={"machine": machine, "hours": (Decimal(row.duration_minutes) * Decimal(row.percent_complete) / Decimal("6000")).quantize(Decimal("0.01")),
                      "source": "typed_manual", "consumable_pool": pools.get(row.filament_spool_id), "duration_minutes": row.duration_minutes,
                      "outcome": row.outcome, "percent_complete": row.percent_complete, "reason": row.reason,
                      "consumed_grams": row.grams_used, "title": row.title, "requester_name": row.requester_name,
                      "contact_email": row.contact_email, "contact_phone": row.contact_phone, "note": row.note, "logged_by": row.logged_by},
        )
        _timestamp(MachineUsageEntry, target.pk, row.created_at)
        manual[row.pk] = target
    for row in FilamentAdjustment.objects.filter(makerspace=makerspace).order_by("created_at", "id"):
        pool = pools.get(row.filament_spool_id)
        if pool is None:
            _repair(makerspace, "invalid_source", "printing.FilamentAdjustment", row.pk, reason="missing imported pool")
            raise CutoverMismatch("Ledger pool missing")
        target, _ = MachineConsumableAdjustment.objects.get_or_create(
            legacy_filament_adjustment_id=row.pk,
            defaults={"consumable_pool": pool, "makerspace": makerspace, "kind": row.kind, "quantity_delta": row.grams,
                      "service_request": requests.get(row.print_request_id), "usage_entry": manual.get(row.manual_log_id),
                      "reason": row.reason, "created_by": row.created_by},
        )
        _timestamp(MachineConsumableAdjustment, target.pk, row.created_at)
    # Pool balance is derived only from imported signed history.  A gap is a
    # repair, never an invented adjustment that would rewrite audit provenance.
    for legacy_id, pool in pools.items():
        total = sum((row.quantity_delta for row in pool.adjustments.all()), Decimal("0"))
        expected = (pool.initial_grams + total).quantize(Decimal("0.01"))
        from apps.printing.models import FilamentSpool
        legacy = FilamentSpool.objects.get(pk=legacy_id)
        if expected != legacy.remaining_weight_grams:
            _repair(makerspace, "mismatch", "printing.FilamentSpool", legacy_id, expected=str(expected), legacy_remaining=str(legacy.remaining_weight_grams))
            raise CutoverMismatch("Ledger balance mismatch")
        MachineConsumablePool.objects.filter(pk=pool.pk).update(remaining_grams=expected)


def reconcile(makerspace):
    """Gate authority on deterministic provenance and aggregate parity."""
    from apps.printing.models import FilamentAdjustment, FilamentSpool, ManualPrintLog, PrintBucket, PrintPrinter, PrintRequest, PrintRequestFile
    pairs = (
        ("printing.PrintPrinter", PrintPrinter.objects.filter(makerspace=makerspace).count(), Machine.objects.filter(makerspace=makerspace, legacy_print_printer_id__isnull=False).count()),
        ("printing.PrintBucket", PrintBucket.objects.filter(makerspace=makerspace).count(), ServiceQueue.objects.filter(makerspace=makerspace, legacy_print_bucket_id__isnull=False).count()),
        ("printing.FilamentSpool", FilamentSpool.objects.filter(makerspace=makerspace).count(), MachineConsumablePool.objects.filter(makerspace=makerspace, legacy_filament_spool_id__isnull=False).count()),
        ("printing.PrintRequest", PrintRequest.objects.filter(bucket__makerspace=makerspace).count(), MachineServiceRequest.objects.filter(makerspace=makerspace, legacy_print_request_id__isnull=False).count()),
        ("printing.PrintRequestFile", PrintRequestFile.objects.filter(makerspace=makerspace).count(), ServiceRequestFile.objects.filter(makerspace=makerspace, legacy_print_request_file_id__isnull=False).count()),
        ("printing.ManualPrintLog", ManualPrintLog.objects.filter(makerspace=makerspace).count(), MachineUsageEntry.objects.filter(machine__makerspace=makerspace, legacy_manual_print_log_id__isnull=False).count()),
        ("printing.FilamentAdjustment", FilamentAdjustment.objects.filter(makerspace=makerspace).count(), MachineConsumableAdjustment.objects.filter(makerspace=makerspace, legacy_filament_adjustment_id__isnull=False).count()),
    )
    bad = [(label, old, new) for label, old, new in pairs if old != new]
    legacy_status = Counter(PrintRequest.objects.filter(bucket__makerspace=makerspace).values_list("status", flat=True))
    kernel_status = Counter(MachineServiceRequest.objects.filter(makerspace=makerspace, legacy_print_request_id__isnull=False).values_list("status", flat=True))
    kernel_status["printing"] = kernel_status.pop("in_progress", 0)
    if legacy_status != kernel_status:
        bad.append(("request_status", dict(legacy_status), dict(kernel_status)))
    old_tokens = set(PrintRequest.objects.filter(bucket__makerspace=makerspace).values_list("public_token", flat=True))
    new_tokens = set(MachineServiceRequest.objects.filter(makerspace=makerspace, legacy_print_request_id__isnull=False).values_list("public_token", flat=True))
    if old_tokens != new_tokens:
        bad.append(("public_tokens", len(old_tokens), len(new_tokens)))
    if bad:
        for label, old, new in bad:
            _repair(makerspace, "mismatch", label, None, legacy=old, kernel=new)
        raise CutoverMismatch("Printing reconciliation failed")
    return {"ok": True, "requests": pairs[3][1], "tokens": len(old_tokens)}


@transaction.atomic
def flip_authority(makerspace, *, actor=None):
    reconcile(makerspace)
    state, _ = PrintingCutoverState.objects.select_for_update().get_or_create(makerspace=makerspace)
    if state.kernel_authoritative_at is None:
        state.kernel_authoritative_at = timezone.now()
        state.save(update_fields=["kernel_authoritative_at", "updated_at"])
        audit.record(actor, "machine_printing.kernel_authority_enabled", makerspace=makerspace, target=state,
                     meta={"rollback": "unsafe; use forward repair"})
    return state
