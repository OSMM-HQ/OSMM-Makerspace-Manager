"""B4 deterministic import, reconciliation, and authority boundary.

This module intentionally has no reverse writer.  Legacy rows are provenance
evidence; after ``flip_authority`` every new print mutation is kernel-only and
repairs add kernel records or repair rows.
"""

from collections import Counter
from decimal import Decimal
import logging

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.audit import services as audit
from apps.machines.models import (
    Machine, MachineConsumableAdjustment, MachineConsumablePool,
    MachineServiceRequest, MachineUsageEntry, PrintingCutoverRepair,
    PrintingCutoverState, ServiceQueue, ServiceRequestFile,
)
from apps.machines.printer_capabilities import PRINTER_SLUG

logger = logging.getLogger(__name__)


class CutoverMismatch(RuntimeError):
    """Raised after durable repair evidence is written for a failed gate."""



    def __init__(self, message, *, repairs=None, details=None):
        super().__init__(message)
        self.repairs = repairs or []
        self.details = details or []
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
                                    "no_filament_preference": True,
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
        for repair in exc.repairs:
            _repair(makerspace, **repair)
        _repair(makerspace, "mismatch", "machines.printing_cutover", None, error=str(exc))
        raise

def _backfill_warranties(makerspace, machines):
    """Warranties are machine-hosted before B7b removes the printer FK."""
    return None


def _backfill_reprints(makerspace, requests):
    from apps.printing.models import PrintRequest
    for legacy in PrintRequest.objects.filter(bucket__makerspace=makerspace, reprint_of__isnull=False):
        child, root = requests[legacy.pk], _legacy_reprint_root(legacy, requests)
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
        root = _legacy_reprint_root(row.print_request, requests) or request
        target, _ = ServiceRequestFile.objects.get_or_create(
            legacy_print_request_file_id=row.pk,
            defaults={"service_request": root, "makerspace": makerspace, "machine": root.assigned_machine,
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
        root = _legacy_reprint_root(legacy, requests) or request
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
        target = MachineUsageEntry.objects.filter(legacy_manual_print_log_id=row.pk).first()
        if target is None:
            target = MachineUsageEntry(
                legacy_manual_print_log_id=row.pk, machine=machine,
                hours=(Decimal(row.duration_minutes) * Decimal(row.percent_complete) / Decimal("6000")).quantize(Decimal("0.01")),
                source="typed_manual", consumable_pool=pools.get(row.filament_spool_id), duration_minutes=row.duration_minutes,
                outcome=row.outcome, percent_complete=row.percent_complete, reason=row.reason,
                consumed_grams=row.grams_used, title=row.title, requester_name=row.requester_name,
                contact_email=row.contact_email, contact_phone=row.contact_phone, note=row.note,
                logged_by=row.logged_by, created_at=row.created_at,
            )
            target.save(preserve_created_at=True)
        manual[row.pk] = target
    for row in FilamentAdjustment.objects.filter(makerspace=makerspace).order_by("created_at", "id"):
        pool = pools.get(row.filament_spool_id)
        if pool is None:
            _repair(makerspace, "invalid_source", "printing.FilamentAdjustment", row.pk, reason="missing imported pool")
            raise CutoverMismatch("Ledger pool missing")
        target = MachineConsumableAdjustment.objects.filter(legacy_filament_adjustment_id=row.pk).first()
        if target is None:
            target = MachineConsumableAdjustment(
                legacy_filament_adjustment_id=row.pk, consumable_pool=pool, makerspace=makerspace,
                kind=row.kind, quantity_delta=row.grams, service_request=requests.get(row.print_request_id),
                usage_entry=manual.get(row.manual_log_id), reason=row.reason,
                created_by=row.created_by, created_at=row.created_at,
            )
            target.save(preserve_created_at=True)
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


def _legacy_reprint_root(legacy, requests):
    """Resolve a legacy reprint chain to its original imported request."""
    seen = set()
    while legacy.reprint_of_id:
        if legacy.pk in seen:
            return None
        seen.add(legacy.pk)
        legacy = legacy.reprint_of
    return requests.get(legacy.pk)


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    return value


def _normalise_report(value):
    """Make ordered/decimal report output safe for deterministic comparison."""
    if isinstance(value, Decimal):
        return round(float(value), 2)
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, dict):
        return {key: _normalise_report(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        normalised = [_normalise_report(item) for item in value]
        if all(isinstance(item, dict) for item in normalised):
            return sorted(normalised, key=lambda item: repr(sorted(item.items())))
        return normalised
    return value


def _storage_reconciliation(makerspace, legacy_requests, legacy_files, kernel_files):
    """Verify imported storage without charging or fabricating replacement objects."""
    from apps.printing.storage import print_object_size

    expected = {}
    for row in legacy_files:
        if row.print_request_id:
            expected[row.object_key] = {
                "legacy_model": "printing.PrintRequestFile", "legacy_id": row.pk,
                "size_bytes": row.size_bytes or None,
            }
    for legacy in legacy_requests:
        for field in ("model_file", "estimate_screenshot", "preview_screenshot"):
            key = getattr(legacy, field).name
            if key:
                expected.setdefault(key, {
                    "legacy_model": "printing.PrintRequest", "legacy_id": legacy.pk,
                    "size_bytes": None,
                })

    actual_keys = set(kernel_files.values_list("object_key", flat=True))
    expected_keys = set(expected)
    bad, repairs = [], []
    if actual_keys != expected_keys:
        bad.append(("storage_object_keys", sorted(expected_keys), sorted(actual_keys)))
    total = 0
    for key in sorted(expected_keys):
        expected_size = expected[key]["size_bytes"]
        actual_size = print_object_size(key)
        if actual_size is None:
            repairs.append({
                "kind": PrintingCutoverRepair.Kind.MISSING_OBJECT,
                "model": expected[key]["legacy_model"], "legacy_id": expected[key]["legacy_id"],
                "object_key": key,
            })
            bad.append(("storage_missing_object", key, None))
            continue
        total += actual_size
        if expected_size is not None and actual_size != expected_size:
            bad.append(("storage_size", key, {"legacy": expected_size, "storage": actual_size}))
    summary = {"objects": len(expected_keys), "bytes": total, "storage_bytes_used": makerspace.storage_bytes_used}
    logger.info("printing_cutover_storage_reconciliation", extra={"makerspace_id": makerspace.pk, **summary})
    if total != makerspace.storage_bytes_used:
        bad.append(("storage_bytes", makerspace.storage_bytes_used, total))
    return bad, repairs, summary


def reconcile(makerspace):
    """Gate authority on deterministic provenance and aggregate parity."""
    from apps.printing.models import FilamentAdjustment, FilamentSpool, ManualPrintLog, PrintBucket, PrintPrinter, PrintRequest, PrintRequestFile

    pairs = (
        ("printing.PrintPrinter", PrintPrinter.objects.filter(makerspace=makerspace).count(), Machine.objects.filter(makerspace=makerspace, legacy_print_printer_id__isnull=False).count()),
        ("printing.PrintBucket", PrintBucket.objects.filter(makerspace=makerspace).count(), ServiceQueue.objects.filter(makerspace=makerspace, legacy_print_bucket_id__isnull=False).count()),
        ("printing.FilamentSpool", FilamentSpool.objects.filter(makerspace=makerspace).count(), MachineConsumablePool.objects.filter(makerspace=makerspace, legacy_filament_spool_id__isnull=False).count()),
        ("printing.PrintRequest", PrintRequest.objects.filter(bucket__makerspace=makerspace).count(), MachineServiceRequest.objects.filter(makerspace=makerspace, legacy_print_request_id__isnull=False).count()),
        ("printing.PrintRequestFile", PrintRequestFile.objects.filter(makerspace=makerspace, print_request_id__isnull=False).count(), ServiceRequestFile.objects.filter(makerspace=makerspace, legacy_print_request_file_id__isnull=False).count()),
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

    legacy_requests = list(PrintRequest.objects.filter(bucket__makerspace=makerspace).select_related("reprint_of"))
    kernel_requests = {
        row.legacy_print_request_id: row
        for row in MachineServiceRequest.objects.filter(
            makerspace=makerspace, legacy_print_request_id__isnull=False,
        ).select_related("reprint_of")
    }
    legacy_roots = {row.pk: kernel_requests.get(row.pk) for row in legacy_requests}
    for legacy in legacy_requests:
        kernel = kernel_requests.get(legacy.pk)
        if kernel is None:
            continue
        payment = (legacy.price, legacy.payment_status, legacy.paid_at, legacy.collected_at, legacy.collected_by_id)
        kernel_payment = (kernel.payment_amount, kernel.payment_status, kernel.paid_at, kernel.collected_at, kernel.collected_by_id)
        if payment != kernel_payment:
            bad.append(("request_payment", legacy.pk, {"legacy": payment, "kernel": kernel_payment}))
        grams = (legacy.estimated_filament_grams, legacy.filament_grams_reserved, legacy.filament_grams_used)
        kernel_grams = (kernel.planned_grams, kernel.reserved_grams, kernel.actual_consumed_grams)
        if grams != kernel_grams:
            bad.append(("request_grams", legacy.pk, {"legacy": grams, "kernel": kernel_grams}))
        root = _legacy_reprint_root(legacy, legacy_roots)
        if legacy.reprint_of_id and kernel.reprint_of_id != getattr(root, "pk", None):
            bad.append(("reprint_root", legacy.pk, {
                "legacy_root": getattr(root, "legacy_print_request_id", None),
                "kernel_root": getattr(kernel.reprint_of, "legacy_print_request_id", None),
            }))

    legacy_files = PrintRequestFile.objects.filter(makerspace=makerspace).select_related("print_request__reprint_of")
    kernel_files = ServiceRequestFile.objects.filter(makerspace=makerspace, service_request__legacy_print_request_id__isnull=False).select_related("service_request")
    for legacy_file in legacy_files:
        if not legacy_file.print_request_id:
            continue
        root = _legacy_reprint_root(legacy_file.print_request, legacy_roots)
        imported = kernel_files.filter(legacy_print_request_file_id=legacy_file.pk).first()
        if imported and imported.service_request_id != getattr(root, "pk", None):
            bad.append(("reprint_attachment_root", legacy_file.pk, {
                "legacy_root": getattr(root, "legacy_print_request_id", None),
                "kernel_request": imported.service_request.legacy_print_request_id,
            }))
    storage_bad, missing_repairs, storage_summary = _storage_reconciliation(
        makerspace, legacy_requests, legacy_files, kernel_files,
    )
    bad.extend(storage_bad)

    from apps.printing.reports import _build_legacy_printing_report
    from apps.printing.reports_kernel import build_kernel_printing_report
    legacy_report = _normalise_report(_build_legacy_printing_report(makerspace.pk))
    kernel_report = _normalise_report(build_kernel_printing_report(makerspace.pk))
    if legacy_report != kernel_report:
        bad.append(("report_json", legacy_report, kernel_report))

    for spool in FilamentSpool.objects.filter(makerspace=makerspace):
        pool = MachineConsumablePool.objects.filter(legacy_filament_spool_id=spool.pk).first()
        if pool is None:
            continue
        legacy_sum = sum((row.grams for row in FilamentAdjustment.objects.filter(filament_spool=spool)), Decimal("0"))
        kernel_sum = sum((row.quantity_delta for row in MachineConsumableAdjustment.objects.filter(consumable_pool=pool)), Decimal("0"))
        if legacy_sum != kernel_sum or spool.remaining_weight_grams != pool.remaining_grams:
            bad.append(("ledger_balance", spool.pk, {
                "legacy_sum": legacy_sum, "kernel_sum": kernel_sum,
                "legacy_remaining": spool.remaining_weight_grams, "kernel_remaining": pool.remaining_grams,
            }))
    if bad:
        for label, old, new in bad:
            _repair(makerspace, "mismatch", label, None, legacy=_json_value(old), kernel=_json_value(new))
        raise CutoverMismatch("Printing reconciliation failed", repairs=missing_repairs)
    return {"ok": True, "requests": pairs[3][1], "tokens": len(old_tokens), "storage": storage_summary}

@transaction.atomic
def flip_authority(makerspace, *, actor=None):
    if "machine_service" not in set(makerspace.enabled_modules or []):
        raise ValidationError(
            "Machine service must remain enabled before printing can use the machine kernel."
        )
    reconcile(makerspace)
    state, _ = PrintingCutoverState.objects.select_for_update().get_or_create(makerspace=makerspace)
    if state.kernel_authoritative_at is None:
        state.kernel_authoritative_at = timezone.now()
        state.save(update_fields=["kernel_authoritative_at", "updated_at"])
        audit.record(actor, "machine_printing.kernel_authority_enabled", makerspace=makerspace, target=state,
                     meta={"rollback": "unsafe; use forward repair"})
    return state
