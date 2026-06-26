from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce

from apps.inventory import public_image_storage
from apps.printing.models import PrintPrinter, PrintRequest
from apps.printing.reports_filament import decimal_to_float

COMPLETED_STATUSES = [PrintRequest.Status.COMPLETED, PrintRequest.Status.COLLECTED]


def printer_hours(requests, include_makerspace, manual_logs=None):
    completed = requests.filter(
        status__in=COMPLETED_STATUSES,
        printer__isnull=False,
    )
    values = ["printer_id", "printer__name", "printer__model"]
    if include_makerspace:
        values.append("printer__makerspace_id")

    rows = (
        completed.values(*values)
        .annotate(completed_requests=Count("id"), minutes=Sum("estimated_minutes"))
        .order_by("printer__makerspace_id", "printer__name", "printer_id")
    )

    data = []
    by_printer = {}
    for row in rows:
        item = {
            "printer_id": row["printer_id"],
            "printer_name": row["printer__name"],
            "printer_model": row["printer__model"] or "",
            "completed_requests": row["completed_requests"],
            "_minutes": row["minutes"] or 0,
        }
        if include_makerspace:
            item["makerspace_id"] = row["printer__makerspace_id"]
        data.append(item)
        by_printer[row["printer_id"]] = item

    if manual_logs is not None:
        _add_manual_hours(data, by_printer, manual_logs, values, include_makerspace)
    for item in data:
        item["hours"] = round(item.pop("_minutes") / 60, 1)
    return data


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
    )
    values = ["printer_id", "printer__name", "printer__model"]
    if include_makerspace:
        values.append("printer__makerspace_id")
    rows = (
        qs.values(*values)
        .annotate(
            completed=Count("id", filter=Q(status__in=COMPLETED_STATUSES)),
            failed=Count("id", filter=Q(status=PrintRequest.Status.FAILED)),
            grams_used=Coalesce(Sum("filament_grams_used"), Decimal("0")),
        )
        .order_by("printer__makerspace_id", "printer__name", "printer_id")
    )
    data = []
    by_printer = {}
    for row in rows:
        item = {
            "printer_id": row["printer_id"],
            "printer_name": row["printer__name"],
            "printer_model": row["printer__model"] or "",
            "completed": row["completed"],
            "failed": row["failed"],
            "grams_used": decimal_to_float(row["grams_used"]),
            "manual_logs": 0,
        }
        if include_makerspace:
            item["makerspace_id"] = row["printer__makerspace_id"]
        data.append(item)
        by_printer[row["printer_id"]] = item
    if manual_logs is not None:
        _add_manual_outcomes(data, by_printer, manual_logs, include_makerspace)
    return data


def _add_manual_hours(data, by_printer, manual_logs, values, include_makerspace):
    manual_rows = (
        manual_logs.filter(printer__isnull=False)
        .values(*values)
        .annotate(manual_minutes=Sum("duration_minutes"))
        .order_by("printer__makerspace_id", "printer__name", "printer_id")
    )
    for row in manual_rows:
        printer_id = row["printer_id"]
        manual_minutes = row["manual_minutes"] or 0
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
        .annotate(manual_grams=Coalesce(Sum("grams_used"), Decimal("0")), manual_count=Count("id"))
        .order_by("printer__makerspace_id", "printer__name", "printer_id")
    )
    for row in manual_rows:
        printer_id = row["printer_id"]
        manual_grams = row["manual_grams"] or Decimal("0")
        if printer_id in by_printer:
            item = by_printer[printer_id]
            item["grams_used"] = decimal_to_float(Decimal(str(item["grams_used"])) + manual_grams)
            item["manual_logs"] = row["manual_count"]
            continue
        item = {
            "printer_id": printer_id,
            "printer_name": row["printer__name"],
            "printer_model": row["printer__model"] or "",
            "completed": 0,
            "failed": 0,
            "grams_used": decimal_to_float(manual_grams),
            "manual_logs": row["manual_count"],
        }
        if include_makerspace:
            item["makerspace_id"] = row["printer__makerspace_id"]
        data.append(item)