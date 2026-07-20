"""Printing-report projection for B4-authoritative machine-kernel rows."""

from collections import defaultdict
from decimal import Decimal

from apps.hardware_requests.display import requester_label_for_user
from apps.inventory import public_image_storage
from apps.printing.reports_filament import decimal_to_float


COMPLETED = {"completed", "collected"}
STATUS = {
    "pending": "pending", "accepted": "accepted", "in_progress": "printing",
    "completed": "completed", "collected": "collected", "rejected": "rejected",
    "failed": "failed",
}


def build_kernel_printing_report(makerspace_id, *, include_makerspace=False, date_range=None):
    from apps.machines.models import (
        MachineConsumableAdjustment, MachineConsumablePool, MachineServiceRequest,
        MachineUsageEntry,
    )

    requests = list(
        MachineServiceRequest.objects.select_related("requester", "assigned_machine")
        .filter(
            makerspace_id=makerspace_id, queue__legacy_print_bucket_id__isnull=False,
            queue__machine_type__slug="3d_printer",
        )
    )
    pools = list(MachineConsumablePool.objects.filter(
        makerspace_id=makerspace_id, legacy_filament_spool_id__isnull=False,
    ))
    manual = list(MachineUsageEntry.objects.select_related("machine").filter(
        machine__makerspace_id=makerspace_id,
        source=MachineUsageEntry.Source.TYPED_MANUAL,
    ))
    request_period = _dated(requests, "created_at", date_range)
    completed = _dated(requests, "completed_at", date_range)
    failed = _dated(requests, "failed_at", date_range)
    manual = _dated(manual, "created_at", date_range)

    return {
        "totals": _totals(request_period),
        "printer_hours": _printer_hours(completed, failed, manual, include_makerspace),
        "printer_outcomes": _printer_outcomes(completed, failed, manual, include_makerspace),
        "filament_used": _filament_used(pools, date_range, include_makerspace, MachineConsumableAdjustment),
        "filament_by_brand": _filament_by_brand(pools, date_range, MachineConsumableAdjustment),
        "top_requesters": _top_requesters(completed, include_makerspace),
        "total_grams_used": _total_grams(pools, date_range, MachineConsumableAdjustment),
        "payments": _payments(completed),
        "filament_estimated_by_period": {
            "by_month": _periods(completed, "%Y-%m", "month"),
            "by_day": _periods(completed, "%Y-%m-%d", "day"),
            "by_hour": _periods(completed, "%Y-%m-%d %H:00", "hour"),
        },
    }


def _dated(rows, field, date_range):
    if not date_range:
        return rows
    start, end = date_range
    return [row for row in rows if getattr(row, field) is not None and (
        (start is None or getattr(row, field) >= start)
        and (end is None or getattr(row, field) < end)
    )]


def _totals(rows):
    counts = defaultdict(int)
    for row in rows:
        counts[STATUS[row.status]] += 1
    return {"total_requests": sum(counts.values()), **{key: counts[key] for key in STATUS.values()}}


def _printer_identity(machine):
    return (
        getattr(machine, "legacy_print_printer_id", None) or machine.pk,
        machine.name, str((machine.type_payload or {}).get("model", "")), machine.makerspace_id,
    )


def _printer_rows(completed, failed, manual, include_makerspace, *, outcomes=False):
    rows, by_key = [], {}
    def item(machine):
        key = _printer_identity(machine)
        if key not in by_key:
            value = {"printer_id": key[0], "printer_name": key[1], "printer_model": key[2]}
            if include_makerspace:
                value["makerspace_id"] = key[3]
            value.update({"completed": 0, "failed": 0, "grams_used": Decimal("0"), "manual_logs": 0} if outcomes else {"completed_requests": 0, "_minutes": Decimal("0")})
            by_key[key] = value
            rows.append(value)
        return by_key[key]
    for request in completed:
        if request.assigned_machine_id:
            value = item(request.assigned_machine)
            if outcomes:
                value["completed"] += 1
                value["grams_used"] += request.actual_consumed_grams or Decimal("0")
            else:
                value["completed_requests"] += 1
                value["_minutes"] += request.actual_minutes or request.run_estimated_minutes or request.estimated_minutes or 0
    for request in failed:
        if request.status != "failed":
            continue
        if request.assigned_machine_id:
            value = item(request.assigned_machine)
            if outcomes:
                value["failed"] += 1
                value["grams_used"] += request.actual_consumed_grams or Decimal("0")
            else:
                value["_minutes"] += Decimal(request.actual_minutes or request.run_estimated_minutes or request.estimated_minutes or 0) * Decimal(request.fail_percent_complete) / 100
    for entry in manual:
        value = item(entry.machine)
        if outcomes:
            value["manual_logs"] += 1
            value["grams_used"] += entry.consumed_grams or Decimal("0")
            value["completed" if entry.outcome == "success" else "failed"] += 1
        else:
            value["_minutes"] += Decimal(entry.duration_minutes) * Decimal(entry.percent_complete) / 100
    rows.sort(key=lambda row: ((row.get("makerspace_id") or 0), row["printer_name"], row["printer_id"]))
    for row in rows:
        if outcomes:
            row["grams_used"] = decimal_to_float(row["grams_used"])
        else:
            row["hours"] = round(float(row.pop("_minutes")) / 60, 1)
    _attach_image_urls(rows)
    return rows


def _printer_hours(completed, failed, manual, include_makerspace):
    return _printer_rows(completed, failed, manual, include_makerspace)


def _printer_outcomes(completed, failed, manual, include_makerspace):
    return _printer_rows(completed, failed, manual, include_makerspace, outcomes=True)


def _attach_image_urls(rows):
    from apps.printing.models import PrintPrinter
    images = {
        row.pk: public_image_storage.public_url(row.image_key) or None
        for row in PrintPrinter.objects.filter(id__in=[item["printer_id"] for item in rows]).only("id", "image_key")
    }
    for row in rows:
        row["image_url"] = images.get(row["printer_id"])


def _pool_grams(pool, date_range, Adjustment):
    adjustments = Adjustment.objects.filter(consumable_pool=pool)
    if date_range:
        start, end = date_range
        if start is not None:
            adjustments = adjustments.filter(created_at__gte=start)
        if end is not None:
            adjustments = adjustments.filter(created_at__lt=end)
    if adjustments.exists():
        return max(-sum((row.quantity_delta for row in adjustments), Decimal("0")), Decimal("0"))
    return max(pool.initial_grams - pool.remaining_grams, Decimal("0"))


def _filament_used(pools, date_range, include_makerspace, Adjustment):
    rows = []
    for pool in sorted(pools, key=lambda row: (row.material, row.color, row.pk)):
        row = {"spool_id": pool.legacy_filament_spool_id or pool.pk, "material": pool.material, "color": pool.color, "grams_used": decimal_to_float(_pool_grams(pool, date_range, Adjustment)), "remaining_grams": decimal_to_float(pool.remaining_grams)}
        if include_makerspace:
            row["makerspace_id"] = pool.makerspace_id
        rows.append(row)
    return rows


def _filament_by_brand(pools, date_range, Adjustment):
    data = {}
    for pool in pools:
        brand = (pool.brand or "").strip() or "Unbranded"
        row = data.setdefault(brand, {"brand": brand, "grams_used": Decimal("0"), "spools": 0})
        row["grams_used"] += _pool_grams(pool, date_range, Adjustment)
        row["spools"] += 1
    rows = [{**row, "grams_used": decimal_to_float(row["grams_used"])} for row in data.values()]
    return sorted(rows, key=lambda row: row["grams_used"], reverse=True)


def _total_grams(pools, date_range, Adjustment):
    return decimal_to_float(sum((_pool_grams(pool, date_range, Adjustment) for pool in pools), Decimal("0")))


def _top_requesters(rows, include_makerspace):
    groups = {}
    for request in rows:
        email = (request.contact_email or "").strip().casefold()
        key = (request.makerspace_id, email) if email else (request.makerspace_id, request.requester_id)
        group = groups.setdefault(key, {"request": request, "requests": 0, "items": 0, "grams": Decimal("0")})
        group["requests"] += 1
        group["items"] += (request.capability_payload or {}).get("quantity", 1)
        if request.status in COMPLETED:
            group["grams"] += request.run_planned_grams or request.planned_grams or Decimal("0")
    data = []
    for group in groups.values():
        request = group["request"]
        label = (request.requester_name or "").strip() or (request.contact_email or "").strip() or requester_label_for_user(username=request.requester.username, external_checkin_user_id=request.requester.external_checkin_user_id)
        row = {"requester_id": request.requester_id, "requester": label or "Anonymous", "grams": decimal_to_float(group["grams"]), "requests": group["requests"], "items": group["items"]}
        if include_makerspace:
            row["makerspace_id"] = request.makerspace_id
        data.append(row)
    return sorted(data, key=lambda row: (-row["grams"], -row["requests"], -row["items"]))


def _payments(rows):
    paid = [row for row in rows if row.payment_status == "paid"]
    outstanding = [row for row in rows if row.payment_status == "pending"]
    return {"paid_amount": sum((row.payment_amount or Decimal("0") for row in paid), Decimal("0")), "paid_count": len(paid), "outstanding_amount": sum((row.payment_amount or Decimal("0") for row in outstanding), Decimal("0")), "outstanding_count": len(outstanding)}


def _periods(rows, fmt, grain):
    totals = defaultdict(lambda: Decimal("0"))
    for row in rows:
        if row.status not in COMPLETED or row.completed_at is None:
            continue
        date = row.completed_at
        if grain == "month":
            date = date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif grain == "day":
            date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            date = date.replace(minute=0, second=0, microsecond=0)
        totals[date] += row.run_planned_grams or row.planned_grams or Decimal("0")
    return [{"period": key.strftime(fmt), "grams": decimal_to_float(value)} for key, value in sorted(totals.items())]
