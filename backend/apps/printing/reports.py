from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce, TruncDay, TruncHour, TruncMonth

from apps.accounts import rbac
from apps.hardware_requests.display import requester_label_for_user
from apps.printing.models import FilamentSpool, ManualPrintLog, PrintRequest
from apps.printing.reports_filament import (
    decimal_to_float,
    estimated_filament_by_period,
    filament_by_brand,
    filament_used,
    total_spool_grams_used,
)
from apps.printing.reports_printer_activity import (
    attach_printer_image_urls,
    printer_hours,
    printer_outcomes,
)

STATUS_KEYS = {
    PrintRequest.Status.COMPLETED: "completed",
    PrintRequest.Status.COLLECTED: "collected",
    PrintRequest.Status.FAILED: "failed",
    PrintRequest.Status.REJECTED: "rejected",
    PrintRequest.Status.PENDING: "pending",
    PrintRequest.Status.PRINTING: "printing",
    PrintRequest.Status.ACCEPTED: "accepted",
}
COMPLETED_STATUSES = [PrintRequest.Status.COMPLETED, PrintRequest.Status.COLLECTED]


def build_printing_report(makerspace_id=None, *, include_makerspace=False):
    requests, spools, manual_logs = _scoped_querysets(makerspace_id)
    printer_hour_rows = printer_hours(requests, include_makerspace, manual_logs)
    printer_outcome_rows = printer_outcomes(requests, include_makerspace, manual_logs)
    attach_printer_image_urls(printer_hour_rows, printer_outcome_rows)

    return {
        "totals": _totals(requests),
        "printer_hours": printer_hour_rows,
        "printer_outcomes": printer_outcome_rows,
        "filament_used": filament_used(spools, include_makerspace),
        "filament_by_brand": filament_by_brand(spools),
        "top_requesters": _top_requesters(requests, include_makerspace),
        "total_grams_used": total_spool_grams_used(spools),
        "payments": _payments(requests),
        "filament_estimated_by_period": {
            "by_month": estimated_filament_by_period(requests, TruncMonth, "%Y-%m"),
            "by_day": estimated_filament_by_period(requests, TruncDay, "%Y-%m-%d"),
            "by_hour": estimated_filament_by_period(requests, TruncHour, "%Y-%m-%d %H:00"),
        },
    }


def _scoped_querysets(makerspace_id):
    requests = PrintRequest.objects.all()
    spools = FilamentSpool.objects.all()
    manual_logs = ManualPrintLog.objects.all()
    if makerspace_id is not None:
        return (
            requests.filter(bucket__makerspace_id=makerspace_id),
            spools.filter(makerspace_id=makerspace_id),
            manual_logs.filter(makerspace_id=makerspace_id),
        )

    excluded = rbac.superadmin_hidden_makerspace_ids() | rbac.archived_makerspace_ids()
    if not excluded:
        return requests, spools, manual_logs
    return (
        requests.exclude(bucket__makerspace_id__in=excluded),
        spools.exclude(makerspace_id__in=excluded),
        manual_logs.exclude(makerspace_id__in=excluded),
    )


def _totals(requests):
    rows = requests.values("status").annotate(count=Count("id"))
    counts = {row["status"]: row["count"] for row in rows}
    totals = {"total_requests": sum(counts.values())}
    for status, key in STATUS_KEYS.items():
        totals[key] = counts.get(status, 0)
    return totals


def _top_requesters(requests, include_makerspace):
    values = ["requester_id", "requester__username", "requester__external_checkin_user_id"]
    if include_makerspace:
        values.append("bucket__makerspace_id")
    order = ["-grams", "-request_count", "-items"]
    if include_makerspace:
        order = ["bucket__makerspace_id", *order]
    rows = (
        requests.values(*values)
        .annotate(
            request_count=Count("id"),
            items=Sum("quantity"),
            grams=Coalesce(
                Sum("estimated_filament_grams", filter=Q(status__in=COMPLETED_STATUSES)),
                Decimal("0"),
            ),
        )
        .order_by(*order)
    )
    data = []
    for row in rows:
        item = {
            "requester_id": row["requester_id"],
            "requester": requester_label_for_user(
                username=row["requester__username"],
                external_checkin_user_id=row["requester__external_checkin_user_id"],
            ),
            "grams": decimal_to_float(row["grams"]),
            "requests": row["request_count"],
            "items": row["items"] or 0,
        }
        if include_makerspace:
            item["makerspace_id"] = row["bucket__makerspace_id"]
        data.append(item)
    return data


def _payments(requests):
    paid = _payment_summary(requests, PrintRequest.PaymentStatus.PAID)
    outstanding = _payment_summary(requests, PrintRequest.PaymentStatus.PENDING)
    return {
        "paid_amount": paid["amount"],
        "paid_count": paid["count"],
        "outstanding_amount": outstanding["amount"],
        "outstanding_count": outstanding["count"],
    }


def _payment_summary(requests, payment_status):
    row = requests.filter(
        payment_status=payment_status,
        status__in=COMPLETED_STATUSES,
    ).aggregate(amount=Sum("price"), count=Count("id"))
    return {"amount": row["amount"] or Decimal("0.00"), "count": row["count"] or 0}