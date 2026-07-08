from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce

from apps.inventory import public_image_storage
from apps.printing.models import ManualPrintLog, PrintPrinter, PrintRequest
from apps.printing.reports_filament import decimal_to_float

COMPLETED_STATUSES = [PrintRequest.Status.COMPLETED, PrintRequest.Status.COLLECTED]


def printer_hours(requests, include_makerspace, manual_logs=None, failed_requests=None):
    completed = requests.filter(
        status__in=COMPLETED_STATUSES,
        printer__isnull=False,
    ).select_related("printer", "bucket")

    data = []
    by_key = {}
    by_printer = {}
    for request in completed:
        key = _request_printer_key(request, include_makerspace)
        item = by_key.get(key)
        if item is None:
            item = _request_printer_item(request, include_makerspace)
            item["completed_requests"] = 0
            item["_minutes"] = 0
            by_key[key] = item
            data.append(item)
            by_printer.setdefault(request.printer_id, item)
        item["completed_requests"] += 1
        item["_minutes"] += request.run_estimated_minutes or request.estimated_minutes or 0

    if failed_requests is not None:
        _add_failed_hours(data, by_key, by_printer, failed_requests, include_makerspace)
    if manual_logs is not None:
        values = ["printer_id", "printer__name", "printer__model"]
        if include_makerspace:
            values.append("printer__makerspace_id")
        _add_manual_hours(data, by_printer, manual_logs, values, include_makerspace)
    data.sort(key=_printer_sort_key)
    for item in data:
        item["hours"] = round(item.pop("_minutes") / 60, 1)
    return data


def _add_failed_hours(data, by_key, by_printer, failed_requests, include_makerspace):
    # A failed print still ran the printer for part of its estimate. Count
    # estimated_minutes * fail_percent_complete / 100 toward printer hours.
    failed = failed_requests.filter(
        status=PrintRequest.Status.FAILED,
        printer__isnull=False,
    ).select_related("printer", "bucket")
    for request in failed:
        key = _request_printer_key(request, include_makerspace)
        partial_minutes = (
            (request.run_estimated_minutes or request.estimated_minutes or 0)
            * (request.fail_percent_complete or 0)
            / 100
        )
        item = by_key.get(key)
        if item is None:
            item = _request_printer_item(request, include_makerspace)
            item["completed_requests"] = 0
            item["_minutes"] = 0
            by_key[key] = item
            data.append(item)
            by_printer.setdefault(request.printer_id, item)
        item["_minutes"] += partial_minutes

def _request_printer_key(request, include_makerspace):
    printer = request.printer
    name = request.run_printer_name or (printer.name if printer else "")
    model = request.run_printer_model or (printer.model if printer else "")
    makerspace_id = (
        printer.makerspace_id if printer else request.bucket.makerspace_id
    )
    key = (request.printer_id, name, model)
    if include_makerspace:
        key = key + (makerspace_id,)
    return key


def _request_printer_item(request, include_makerspace):
    printer = request.printer
    item = {
        "printer_id": request.printer_id,
        "printer_name": request.run_printer_name or (printer.name if printer else ""),
        "printer_model": request.run_printer_model or (printer.model if printer else ""),
    }
    if include_makerspace:
        item["makerspace_id"] = printer.makerspace_id if printer else request.bucket.makerspace_id
    return item


def _printer_sort_key(item):
    return (
        item.get("makerspace_id") or 0,
        item.get("printer_name") or "",
        item.get("printer_id") or 0,
    )

def attach_printer_image_urls(*row_groups):
    printer_ids = {
        row.get("printer_id")
        for rows in row_groups
        for row in rows
        if row.get("printer_id")
    }
    if not printer_ids:
        return
    urls = {
        printer.id: public_image_storage.public_url(printer.image_key) or None
        for printer in PrintPrinter.objects.filter(id__in=printer_ids).only("id", "image_key")
    }
    for rows in row_groups:
        for row in rows:
            row["image_url"] = urls.get(row.get("printer_id"))


def printer_outcomes(requests, include_makerspace, manual_logs=None):
    qs = requests.filter(
        printer__isnull=False,
        status__in=COMPLETED_STATUSES + [PrintRequest.Status.FAILED],
    ).select_related("printer", "bucket")
    data = []
    by_key = {}
    by_printer = {}
    for request in qs:
        key = _request_printer_key(request, include_makerspace)
        item = by_key.get(key)
        if item is None:
            item = _request_printer_item(request, include_makerspace)
            item.update({"completed": 0, "failed": 0, "grams_used": Decimal("0"), "manual_logs": 0})
            by_key[key] = item
            data.append(item)
            by_printer.setdefault(request.printer_id, item)
        if request.status in COMPLETED_STATUSES:
            item["completed"] += 1
        elif request.status == PrintRequest.Status.FAILED:
            item["failed"] += 1
        item["grams_used"] += request.filament_grams_used or Decimal("0")

    if manual_logs is not None:
        _add_manual_outcomes(data, by_printer, manual_logs, include_makerspace)
    data.sort(key=_printer_sort_key)
    for item in data:
        item["grams_used"] = decimal_to_float(item["grams_used"])
    return data

def _add_manual_hours(data, by_printer, manual_logs, values, include_makerspace):
    # Weight each manual log's run-time by its completion: a success is 100%
    # (full duration), a failed log counts duration * percent_complete / 100.
    manual_rows = (
        manual_logs.filter(printer__isnull=False)
        .values(*values)
        .annotate(weighted=Sum(F("duration_minutes") * F("percent_complete")))
        .order_by("printer__makerspace_id", "printer__name", "printer_id")
    )
    for row in manual_rows:
        printer_id = row["printer_id"]
        manual_minutes = (row["weighted"] or 0) / 100
        if printer_id in by_printer:
            by_printer[printer_id]["_minutes"] += manual_minutes
            continue
        item = {
            "printer_id": printer_id,
            "printer_name": row["printer__name"],
            "printer_model": row["printer__model"] or "",
            "completed_requests": 0,
            "_minutes": manual_minutes,
        }
        if include_makerspace:
            item["makerspace_id"] = row["printer__makerspace_id"]
        data.append(item)
        by_printer[printer_id] = item


def _add_manual_outcomes(data, by_printer, manual_logs, include_makerspace):
    values = ["printer_id", "printer__name", "printer__model"]
    if include_makerspace:
        values.append("printer__makerspace_id")
    manual_rows = (
        manual_logs.filter(printer__isnull=False)
        .values(*values)
        .annotate(
            manual_grams=Coalesce(Sum("grams_used"), Decimal("0")),
            manual_count=Count("id"),
            manual_failed=Count(
                "id", filter=Q(outcome=ManualPrintLog.Outcome.FAILED)
            ),
            manual_success=Count(
                "id", filter=Q(outcome=ManualPrintLog.Outcome.SUCCESS)
            ),
        )
        .order_by("printer__makerspace_id", "printer__name", "printer_id")
    )
    for row in manual_rows:
        printer_id = row["printer_id"]
        manual_grams = row["manual_grams"] or Decimal("0")
        manual_failed = row["manual_failed"] or 0
        manual_success = row["manual_success"] or 0
        if printer_id in by_printer:
            item = by_printer[printer_id]
            item["grams_used"] = decimal_to_float(Decimal(str(item["grams_used"])) + manual_grams)
            item["manual_logs"] = row["manual_count"]
            item["failed"] = (item.get("failed") or 0) + manual_failed
            item["completed"] = (item.get("completed") or 0) + manual_success
            continue
        item = {
            "printer_id": printer_id,
            "printer_name": row["printer__name"],
            "printer_model": row["printer__model"] or "",
            "completed": manual_success,
            "failed": manual_failed,
            "grams_used": decimal_to_float(manual_grams),
            "manual_logs": row["manual_count"],
        }
        if include_makerspace:
            item["makerspace_id"] = row["printer__makerspace_id"]
        data.append(item)


