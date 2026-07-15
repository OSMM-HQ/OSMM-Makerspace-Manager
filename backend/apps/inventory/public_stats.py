from django.db.models import Count, F, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.inventory.public_stats_hardware import (
    current_loans as _current_loans,
    hardware_stats as _hardware_stats,
    public_display_name,
)
from apps.makerspaces.platform import module_enabled
from apps.machines.public_stats import build_public_machine_stats
from apps.printing.models import ManualPrintLog, PrintRequest
from apps.printing.reports import STATUS_KEYS
from apps.printing.reports_filament import (
    estimated_filament_by_period,
    filament_by_brand,
    total_spool_grams_used,
)
from apps.printing.reports_printer_activity import (
    attach_printer_image_urls,
    printer_hours,
    printer_outcomes,
)
from apps.printing.models import FilamentSpool


PRINT_STATUS_KEYS = (
    "pending",
    "accepted",
    "printing",
    "completed",
    "collected",
    "failed",
    "rejected",
)
COMPLETED_PRINT_STATUSES = (
    PrintRequest.Status.COMPLETED,
    PrintRequest.Status.COLLECTED,
)


def build_public_stats(makerspace) -> dict:
    return {
        'machines': build_public_machine_stats(makerspace),
        "printing": _printing_stats(makerspace),
        "hardware": _hardware_stats(makerspace),
        "current_loans": _current_loans(makerspace),
    }


def _printing_stats(makerspace):
    if not module_enabled(makerspace, "printing"):
        return None
    report = build_printing_report(makerspace.id)
    stats = _project_printing(report)
    stats["hours_this_month"] = _printing_hours_this_month(makerspace.id)
    return stats


def build_printing_report(makerspace_id):
    requests = PrintRequest.objects.filter(bucket__makerspace_id=makerspace_id)
    spools = FilamentSpool.objects.filter(makerspace_id=makerspace_id)
    manual_logs = ManualPrintLog.objects.filter(makerspace_id=makerspace_id)
    # `requests` is unfiltered here (all-time), so failed jobs' partial run-time
    # is included by passing the same queryset as failed_requests (printer_hours
    # filters status=FAILED internally).
    printer_hour_rows = printer_hours(requests, False, manual_logs, failed_requests=requests)
    printer_outcome_rows = printer_outcomes(requests, False, manual_logs)
    attach_printer_image_urls(printer_hour_rows, printer_outcome_rows)
    status_rows = requests.values("status").annotate(count=Count("id"))
    counts = {row["status"]: row["count"] for row in status_rows}
    return {
        "totals": {
            key: counts.get(status, 0)
            for status, key in STATUS_KEYS.items()
        },
        "printer_hours": printer_hour_rows,
        "printer_outcomes": printer_outcome_rows,
        "filament_by_brand": filament_by_brand(spools),
        "total_grams_used": total_spool_grams_used(spools),
        "filament_estimated_by_period": {
            "by_month": estimated_filament_by_period(requests, TruncMonth, "%Y-%m"),
        },
    }


def _project_printing(report):
    totals = report.get("totals") or {}
    printer_hours = report.get("printer_hours") or []
    busiest = max(printer_hours, key=lambda row: row.get("hours") or 0, default=None)
    status_counts = {key: totals.get(key, 0) for key in PRINT_STATUS_KEYS}

    return {
        "hours_all_time": _float(sum(row.get("hours") or 0 for row in printer_hours)),
        "hours_this_month": 0.0,
        "busiest_printer": _public_printer_row(busiest),
        "per_printer": _per_printer(report),
        "grams_all_time": _float(report.get("total_grams_used")),
        "by_brand": [
            {"brand": row.get("brand") or "Unbranded", "grams": _float(row.get("grams_used"))}
            for row in report.get("filament_by_brand") or []
        ],
        "jobs": {
            "completed": totals.get("completed", 0),
            "status_counts": status_counts,
            "queue": {
                "pending": totals.get("pending", 0),
                "accepted": totals.get("accepted", 0),
                "printing": totals.get("printing", 0),
            },
        },
        "filament_trend": [
            {"period": row.get("period"), "grams": _float(row.get("grams"))}
            for row in (report.get("filament_estimated_by_period") or {}).get("by_month", [])
        ],
    }


def _per_printer(report):
    hours_by_printer = {
        row.get("printer_id"): row for row in report.get("printer_hours") or []
    }
    outcomes_by_printer = {
        row.get("printer_id"): row for row in report.get("printer_outcomes") or []
    }
    printer_ids = set(hours_by_printer) | set(outcomes_by_printer)
    rows = []
    for printer_id in printer_ids:
        hours_row = hours_by_printer.get(printer_id) or {}
        outcome_row = outcomes_by_printer.get(printer_id) or {}
        rows.append(
            {
                "name": hours_row.get("printer_name") or outcome_row.get("printer_name") or "",
                "model": hours_row.get("printer_model") or outcome_row.get("printer_model") or "",
                "jobs": outcome_row.get("completed") or 0,
                "hours": _float(hours_row.get("hours")),
                "grams": _float(outcome_row.get("grams_used")),
                "image_url": hours_row.get("image_url") or outcome_row.get("image_url"),
            }
        )
    rows.sort(key=lambda row: (-row["jobs"], -row["grams"], -row["hours"], row["name"]))
    return rows


def _public_printer_row(row):
    if row is None:
        return None
    return {
        "name": row.get("printer_name") or "",
        "model": row.get("printer_model") or "",
        "hours": _float(row.get("hours")),
        "completed": row.get("completed_requests") or 0,
        "image_url": row.get("image_url"),
    }


def _printing_hours_this_month(makerspace_id):
    start, end = _current_month_window()
    request_minutes = sum(
        request.run_estimated_minutes or request.estimated_minutes or 0
        for request in PrintRequest.objects.filter(
            bucket__makerspace_id=makerspace_id,
            status__in=COMPLETED_PRINT_STATUSES,
            completed_at__gte=start,
            completed_at__lt=end,
        ).only("run_estimated_minutes", "estimated_minutes")
    )    # Weight manual minutes by completion to match the all-time report: a success
    # is 100% (full duration), a failed log counts duration * percent_complete / 100.
    manual_weighted = (
        ManualPrintLog.objects.filter(
            makerspace_id=makerspace_id,
            created_at__gte=start,
            created_at__lt=end,
        ).aggregate(total=Sum(F("duration_minutes") * F("percent_complete")))["total"]
        or 0
    )
    manual_minutes = manual_weighted / 100
    # Failed prints this month contribute partial run-time (minutes x percent/100),
    # date-windowed on failed_at since they have no completed_at.
    failed_minutes = sum(
        (request.run_estimated_minutes or request.estimated_minutes or 0)
        * (request.fail_percent_complete or 0)
        / 100
        for request in PrintRequest.objects.filter(
            bucket__makerspace_id=makerspace_id,
            status=PrintRequest.Status.FAILED,
            failed_at__gte=start,
            failed_at__lt=end,
        ).only("run_estimated_minutes", "estimated_minutes", "fail_percent_complete")
    )
    return _float((request_minutes + manual_minutes + failed_minutes) / 60)


def _current_month_window():
    now = timezone.localtime(timezone.now())
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _float(value):
    return round(float(value or 0), 2)


