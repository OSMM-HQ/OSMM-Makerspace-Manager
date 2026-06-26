import re

from django.db.models import Count, F, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.hardware_requests.display import is_internal_checkin_username
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem
from apps.hardware_requests.self_checkout_models import PublicToolLoan
from apps.inventory.models import InventoryProduct, PublicAvailabilityMode
from apps.makerspaces.platform import module_enabled
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
ACTIVE_LOAN_STATUSES = (
    HardwareRequest.Status.ISSUED,
    HardwareRequest.Status.PARTIALLY_RETURNED,
)
COMPLETED_PRINT_STATUSES = (
    PrintRequest.Status.COMPLETED,
    PrintRequest.Status.COLLECTED,
)


def public_display_name(*, request=None, requester=None) -> str:
    candidates = []
    if request is not None:
        label = _safe_public_requester_name(getattr(request, "requester_name", ""))
        if label:
            return label
        candidates.append(getattr(request, "requester_username", ""))
        requester = requester or getattr(request, "requester", None)
    if requester is not None:
        get_full_name = getattr(requester, "get_full_name", None)
        if callable(get_full_name):
            candidates.append(get_full_name())
        candidates.append(getattr(requester, "username", ""))

    for value in candidates:
        label = _clean_label(value)
        if _safe_public_name(label):
            return label
    return "Member"


def build_public_stats(makerspace) -> dict:
    return {
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
    printer_hour_rows = printer_hours(requests, False, manual_logs)
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
    request_minutes = (
        PrintRequest.objects.filter(
            bucket__makerspace_id=makerspace_id,
            status__in=COMPLETED_PRINT_STATUSES,
            completed_at__gte=start,
            completed_at__lt=end,
        ).aggregate(total=Sum("estimated_minutes"))["total"]
        or 0
    )
    manual_minutes = (
        ManualPrintLog.objects.filter(
            makerspace_id=makerspace_id,
            created_at__gte=start,
            created_at__lt=end,
        ).aggregate(total=Sum("duration_minutes"))["total"]
        or 0
    )
    return _float((request_minutes + manual_minutes) / 60)


def _hardware_stats(makerspace):
    products = _public_products(makerspace)
    exact_count_products = _public_exact_count_products(products)
    return {
        "most_popular": _most_popular(makerspace),
        "tools_out": [
            {"name": product.name, "quantity_out": product.issued_quantity}
            for product in exact_count_products.filter(issued_quantity__gt=0).order_by(
                "name", "id"
            )
        ],
        "library": _library_counts(products, exact_count_products),
        "recently_added": _recently_added(products),
    }


def _most_popular(makerspace):
    rows = (
        HardwareRequestItem.objects.filter(
            request__makerspace=makerspace,
            product__is_public=True,
            product__is_archived=False,
            issued_quantity__gt=0,
        )
        .values("product_id", "product__name")
        .annotate(
            times_lent=Count("request_id", distinct=True),
            total_quantity_lent=Sum("issued_quantity"),
        )
        .order_by("-times_lent", "-total_quantity_lent", "product__name", "product_id")
    )
    return [
        {
            "name": row["product__name"],
            "times_lent": row["times_lent"],
            "total_quantity_lent": row["total_quantity_lent"] or 0,
        }
        for row in rows
    ]


def _library_counts(products, exact_count_products):
    totals = exact_count_products.aggregate(
        currently_out_count=Sum("issued_quantity"),
        available_count=Sum("available_quantity"),
    )
    return {
        "currently_out_count": totals["currently_out_count"] or 0,
        "library_size": products.count(),
        "available_count": totals["available_count"] or 0,
    }


def _recently_added(products):
    start, end = _current_month_window()
    return [
        {"name": product.name, "created_at": product.created_at}
        for product in products.filter(created_at__gte=start, created_at__lt=end).order_by(
            "-created_at", "-id"
        )
    ]


def _current_loans(makerspace):
    queryset = (
        HardwareRequestItem.objects.select_related(
            "product",
            "request",
            "request__requester",
            "request__public_tool_loan",
            "request__public_tool_loan__requester",
        )
        .filter(
            request__makerspace=makerspace,
            request__status__in=ACTIVE_LOAN_STATUSES,
            product__is_public=True,
            product__is_archived=False,
        )
        .exclude(product__public_availability_mode=PublicAvailabilityMode.HIDDEN)
        .annotate(
            outstanding=(
                F("issued_quantity")
                - F("returned_quantity")
                - F("damaged_quantity")
                - F("missing_quantity")
            )
        )
        .filter(outstanding__gt=0)
        .order_by("-request__issued_at", "request_id", "id")
    )
    rows = []
    for item in queryset:
        loan = _public_tool_loan(item.request)
        rows.append(
            {
                "item_name": item.product.name,
                "holder_name": public_display_name(
                    request=item.request,
                    requester=(loan.requester if loan else item.request.requester),
                ),
                "due": (loan.due_at if loan else None) or item.request.return_due_at,
                "since": (loan.checked_out_at if loan else None) or item.request.issued_at,
            }
        )
    return rows


def _public_products(makerspace):
    return InventoryProduct.objects.filter(
        makerspace=makerspace,
        is_public=True,
        is_archived=False,
    )


def _public_exact_count_products(products):
    return products.filter(
        public_availability_mode=PublicAvailabilityMode.EXACT_COUNT,
        show_public_count=True,
    )


def _public_tool_loan(request):
    try:
        loan = request.public_tool_loan
    except PublicToolLoan.DoesNotExist:
        return None
    return loan if loan.status == PublicToolLoan.Status.CHECKED_OUT else None


def _current_month_window():
    now = timezone.localtime(timezone.now())
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _clean_label(value):
    return str(value or "").strip()


def _safe_public_name(value):
    if not value or "@" in value or _is_internal_checkin_label(value):
        return False
    # Reject phone-shaped labels even when digits are separated by spaces / ()+-
    # (e.g. "555-123-4567") by normalizing to digits before counting.
    return len(re.sub(r"\D", "", value)) < 7


def _safe_public_requester_name(value):
    label = "".join(char for char in _clean_label(value) if char.isprintable()).strip()
    if not _has_visible_text(label) or not _safe_public_name(label):
        return ""
    return label[:60]


def _has_visible_text(value):
    return any(not char.isspace() and char.isprintable() for char in value)


def _is_internal_checkin_label(value):
    return value.lower().startswith("checkin_") or is_internal_checkin_username(value)


def _float(value):
    return round(float(value or 0), 2)
