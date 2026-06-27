from decimal import Decimal

from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import Coalesce, Lower, TruncDay, TruncHour, TruncMonth

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


def build_printing_report(makerspace_id=None, *, include_makerspace=False, date_range=None):
    requests, spools, manual_logs = _scoped_querysets(makerspace_id)
    request_period = _apply_date_range(requests, "created_at", date_range)
    completed_period = _apply_date_range(requests, "completed_at", date_range)
    # Failed jobs have no completed_at, so they're date-windowed on failed_at and
    # passed separately so their partial run-time counts toward printer hours.
    failed_period = _apply_date_range(requests, "failed_at", date_range)
    manual_period = _apply_date_range(manual_logs, "created_at", date_range)
    printer_hour_rows = printer_hours(
        completed_period, include_makerspace, manual_period, failed_requests=failed_period
    )
    printer_outcome_rows = printer_outcomes(completed_period, include_makerspace, manual_period)
    attach_printer_image_urls(printer_hour_rows, printer_outcome_rows)

    return {
        "totals": _totals(request_period),
        "printer_hours": printer_hour_rows,
        "printer_outcomes": printer_outcome_rows,
        "filament_used": filament_used(spools, include_makerspace),
        "filament_by_brand": filament_by_brand(spools),
        "top_requesters": _top_requesters(completed_period, include_makerspace),
        "total_grams_used": total_spool_grams_used(spools),
        "payments": _payments(completed_period),
        "filament_estimated_by_period": {
            "by_month": estimated_filament_by_period(completed_period, TruncMonth, "%Y-%m"),
            "by_day": estimated_filament_by_period(completed_period, TruncDay, "%Y-%m-%d"),
            "by_hour": estimated_filament_by_period(completed_period, TruncHour, "%Y-%m-%d %H:00"),
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


def _apply_date_range(qs, field, date_range):
    if not date_range:
        return qs
    start, end = date_range
    if start is not None:
        qs = qs.filter(**{f"{field}__gte": start})
    if end is not None:
        qs = qs.filter(**{f"{field}__lt": end})
    return qs


def _totals(requests):
    rows = requests.values("status").annotate(count=Count("id"))
    counts = {row["status"]: row["count"] for row in rows}
    totals = {"total_requests": sum(counts.values())}
    for status, key in STATUS_KEYS.items():
        totals[key] = counts.get(status, 0)
    return totals


def _top_requesters(requests, include_makerspace):
    # Group by the requester's contact email (the human identity entered on every
    # request) but DISPLAY their name. This is a deliberate REPORTING choice: it
    # collapses one person's prints -- even across separate shadow-user rows -- into
    # a single leaderboard line. It does not change auth/identity anywhere. Rows
    # without a contact email fall back to the original requester-id grouping/label.
    grams_filter = Q(status__in=COMPLETED_STATUSES)
    grams = Coalesce(Sum("estimated_filament_grams", filter=grams_filter), Decimal("0"))

    email_keys = ["email_key"]
    if include_makerspace:
        email_keys.append("bucket__makerspace_id")
    email_rows = (
        requests.exclude(contact_email="")
        .annotate(email_key=Lower("contact_email"))
        .values(*email_keys)
        .annotate(
            request_count=Count("id"),
            items=Sum("quantity"),
            grams=grams,
            # Max ignores blank "" in favour of a real name; a stable representative
            # id keeps the serializer's requester_id contract + React keys intact.
            display_name=Max("requester_name"),
            display_email=Max("contact_email"),
            rep_requester_id=Max("requester_id"),
        )
    )
    data = []
    for row in email_rows:
        name = (
            (row["display_name"] or "").strip()
            or (row["display_email"] or "").strip()
            or "Anonymous"
        )
        item = {
            "requester_id": row["rep_requester_id"],
            "requester": name,
            "grams": decimal_to_float(row["grams"]),
            "requests": row["request_count"],
            "items": row["items"] or 0,
        }
        if include_makerspace:
            item["makerspace_id"] = row["bucket__makerspace_id"]
        data.append(item)

    legacy_values = ["requester_id", "requester__username", "requester__external_checkin_user_id"]
    if include_makerspace:
        legacy_values.append("bucket__makerspace_id")
    legacy_rows = (
        requests.filter(contact_email="")
        .values(*legacy_values)
        .annotate(request_count=Count("id"), items=Sum("quantity"), grams=grams)
    )
    for row in legacy_rows:
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

    data.sort(
        key=lambda item: (
            item["makerspace_id"] if include_makerspace else 0,
            -item["grams"],
            -item["requests"],
            -item["items"],
        )
    )
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