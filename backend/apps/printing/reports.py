from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce, TruncDay, TruncHour, TruncMonth

from apps.accounts import rbac
from apps.hardware_requests.display import requester_label_for_user
from apps.inventory import public_image_storage
from apps.printing.models import FilamentSpool, ManualPrintLog, PrintPrinter, PrintRequest


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
    requests = PrintRequest.objects.all()
    spools = FilamentSpool.objects.all()
    manual_logs = ManualPrintLog.objects.all()
    if makerspace_id is not None:
        requests = requests.filter(bucket__makerspace_id=makerspace_id)
        spools = spools.filter(makerspace_id=makerspace_id)
        manual_logs = manual_logs.filter(makerspace_id=makerspace_id)
    else:
        excluded = (
            rbac.superadmin_hidden_makerspace_ids()
            | rbac.archived_makerspace_ids()
        )
        if excluded:
            requests = requests.exclude(bucket__makerspace_id__in=excluded)
            spools = spools.exclude(makerspace_id__in=excluded)
            manual_logs = manual_logs.exclude(makerspace_id__in=excluded)

    printer_hours = _printer_hours(requests, include_makerspace, manual_logs)
    printer_outcomes = _printer_outcomes(
        requests,
        include_makerspace,
        manual_logs,
    )
    _attach_printer_image_urls(printer_hours, printer_outcomes)

    return {
        "totals": _totals(requests),
        # Printer hours combine completed-request estimated minutes AND manual-log
        # durations so ad-hoc prints logged manually are not missing from the hours.
        "printer_hours": printer_hours,
        # Per-printer activity axis: completed request grams are estimate-based
        # because workflow.complete reconciles filament_grams_used from
        # estimated_filament_grams. ManualPrintLog grams are added here as
        # printer activity, not as another spool-delta source.
        "printer_outcomes": printer_outcomes,
        # Per-spool inventory axis: grams are initial-minus-remaining deltas.
        # Manual logs already affect this when they decrement remaining weight.
        "filament_used": _filament_used(spools, include_makerspace),
        "filament_by_brand": _filament_by_brand(spools),
        "top_requesters": _top_requesters(requests, include_makerspace),
        "total_grams_used": _total_spool_grams_used(spools),
        "payments": _payments(requests),
        "filament_estimated_by_period": {
            "by_month": _estimated_filament_by_period(requests, TruncMonth, "%Y-%m"),
            "by_day": _estimated_filament_by_period(requests, TruncDay, "%Y-%m-%d"),
            "by_hour": _estimated_filament_by_period(
                requests,
                TruncHour,
                "%Y-%m-%d %H:00",
            ),
        },
    }


def _totals(requests):
    rows = requests.values("status").annotate(count=Count("id"))
    counts = {row["status"]: row["count"] for row in rows}
    totals = {"total_requests": sum(counts.values())}
    for status, key in STATUS_KEYS.items():
        totals[key] = counts.get(status, 0)
    return totals


def _printer_hours(requests, include_makerspace, manual_logs=None):
    completed = requests.filter(
        status__in=COMPLETED_STATUSES,
        printer__isnull=False,
    )
    values = ["printer_id", "printer__name"]
    if include_makerspace:
        values.append("printer__makerspace_id")

    rows = (
        completed.values(*values)
        .annotate(
            completed_requests=Count("id"),
            minutes=Sum("estimated_minutes"),
        )
        .order_by("printer__makerspace_id", "printer__name", "printer_id")
    )

    data = []
    by_printer = {}
    for row in rows:
        item = {
            "printer_id": row["printer_id"],
            "printer_name": row["printer__name"],
            "completed_requests": row["completed_requests"],
            # Track raw minutes so manual durations can be added before rounding.
            "_minutes": row["minutes"] or 0,
        }
        if include_makerspace:
            item["makerspace_id"] = row["printer__makerspace_id"]
        data.append(item)
        by_printer[row["printer_id"]] = item

    # Add manual-log durations as printer activity (a manual print still ran on the
    # machine). Printers with only manual logs and no completed requests get a row.
    if manual_logs is not None:
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
                "completed_requests": 0,
                "_minutes": manual_minutes,
            }
            if include_makerspace:
                item["makerspace_id"] = row["printer__makerspace_id"]
            data.append(item)
            by_printer[printer_id] = item

    for item in data:
        item["hours"] = round(item.pop("_minutes") / 60, 1)
    return data


def _attach_printer_image_urls(*row_groups):
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


def _printer_outcomes(requests, include_makerspace, manual_logs=None):
    from django.db.models import Q
    from django.db.models.functions import Coalesce

    # Request-outcome grams are per printer. For completed requests,
    # filament_grams_used is reconciled from the operator's estimate at
    # completion time, so it must be presented as estimate-based rather than a
    # measured actual. This aggregation intentionally remains separate from the
    # spool-delta reports below.
    qs = requests.filter(
        printer__isnull=False,
        status__in=COMPLETED_STATUSES + [PrintRequest.Status.FAILED],
    )
    values = ["printer_id", "printer__name"]
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
            "completed": row["completed"],
            "failed": row["failed"],
            "grams_used": _decimal_to_float(row["grams_used"]),
            "manual_logs": 0,
        }
        if include_makerspace:
            item["makerspace_id"] = row["printer__makerspace_id"]
        data.append(item)
        by_printer[row["printer_id"]] = item
    if manual_logs is None:
        return data
    # Manual logs are raw per-printer activity. They also decrement spools when
    # logged through the service, so callers must not add this aggregation to
    # spool-delta totals such as filament_used or total_grams_used.
    values = ["printer_id", "printer__name"]
    if include_makerspace:
        values.append("printer__makerspace_id")
    manual_rows = (
        manual_logs.filter(printer__isnull=False)
        .values(*values)
        .annotate(
            manual_grams=Coalesce(Sum("grams_used"), Decimal("0")),
            manual_count=Count("id"),
        )
        .order_by("printer__makerspace_id", "printer__name", "printer_id")
    )
    for row in manual_rows:
        printer_id = row["printer_id"]
        manual_grams = row["manual_grams"] or Decimal("0")
        if printer_id in by_printer:
            item = by_printer[printer_id]
            item["grams_used"] = _decimal_to_float(
                Decimal(str(item["grams_used"])) + manual_grams
            )
            item["manual_logs"] = row["manual_count"]
            continue
        item = {
            "printer_id": printer_id,
            "printer_name": row["printer__name"],
            "completed": 0,
            "failed": 0,
            "grams_used": _decimal_to_float(manual_grams),
            "manual_logs": row["manual_count"],
        }
        if include_makerspace:
            item["makerspace_id"] = row["printer__makerspace_id"]
        data.append(item)
    return data


def _filament_by_brand(spools):
    # Which filament brand is used most: total spool delta (initial - remaining)
    # summed across every spool of that brand, ranked high-to-low. Brand totals
    # are global (the natural reading of "most-used brand"), so no per-makerspace
    # split. This is the spool-inventory axis, not the completed-request estimate
    # axis used by _printer_outcomes and _estimated_filament_by_period.
    totals = {}
    for spool in spools.only("brand", "initial_weight_grams", "remaining_weight_grams"):
        brand = (spool.brand or "").strip() or "Unbranded"
        entry = totals.setdefault(brand, {"grams": Decimal("0"), "spools": 0})
        entry["grams"] += _spool_grams_used(spool)
        entry["spools"] += 1
    rows = [
        {"brand": brand, "grams_used": _decimal_to_float(data["grams"]), "spools": data["spools"]}
        for brand, data in totals.items()
    ]
    rows.sort(key=lambda row: row["grams_used"], reverse=True)
    return rows


def _top_requesters(requests, include_makerspace):
    # Top printers by FILAMENT GRAMS: total estimated grams printed per requester,
    # ranked high-to-low (the requester who printed the most grams wins). Grams are
    # the operator slicer estimate, summed over completed/collected jobs only.
    # In aggregate mode rows are ordered per makerspace first so the frontend can
    # present a separate ranking per makerspace (not one blended cross-OSMM list).
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
                Sum(
                    "estimated_filament_grams",
                    filter=Q(status__in=COMPLETED_STATUSES),
                ),
                Decimal("0"),
            ),
        )
        .order_by(*order)
    )
    data = []
    for row in rows:
        item = {
            "requester_id": row["requester_id"],
            # Readable label, never the internal checkin_<hash> username.
            "requester": requester_label_for_user(
                username=row["requester__username"],
                external_checkin_user_id=row["requester__external_checkin_user_id"],
            ),
            "grams": _decimal_to_float(row["grams"]),
            "requests": row["request_count"],
            "items": row["items"] or 0,
        }
        if include_makerspace:
            item["makerspace_id"] = row["bucket__makerspace_id"]
        data.append(item)
    return data


def _filament_used(spools, include_makerspace):
    # Per-spool inventory delta. This includes manual usage indirectly when
    # manual logs decrement remaining_weight_grams; keep it separate from
    # per-printer request/manual-log activity in _printer_outcomes.
    data = []
    for spool in spools.order_by("makerspace_id", "material", "color", "id"):
        item = {
            "spool_id": spool.id,
            "material": spool.material,
            "color": spool.color,
            "grams_used": _decimal_to_float(_spool_grams_used(spool)),
            "remaining_grams": _decimal_to_float(spool.remaining_weight_grams),
        }
        if include_makerspace:
            item["makerspace_id"] = spool.makerspace_id
        data.append(item)
    return data


def _total_spool_grams_used(spools):
    # Aggregate of the spool-delta axis only. It is intentionally not the sum of
    # printer_outcomes grams because completed request grams are estimate-based
    # and manual log grams are already reflected in spool deltas.
    total = Decimal("0")
    for spool in spools.only(
        "initial_weight_grams",
        "remaining_weight_grams",
    ):
        total += _spool_grams_used(spool)
    return _decimal_to_float(total)


def _spool_grams_used(spool):
    return max(
        spool.initial_weight_grams - spool.remaining_weight_grams,
        Decimal("0"),
    )


def _estimated_filament_by_period(requests, trunc, period_format):
    # Completed-request period reporting uses the operator estimate captured on
    # the request. There is no measured actual-grams input for completed prints.
    rows = (
        requests.filter(
            status__in=COMPLETED_STATUSES,
            completed_at__isnull=False,
            estimated_filament_grams__isnull=False,
        )
        .annotate(period=trunc("completed_at"))
        .values("period")
        .annotate(grams=Sum("estimated_filament_grams"))
        .order_by("period")
    )
    return [
        {
            "period": row["period"].strftime(period_format),
            "grams": _decimal_to_float(row["grams"] or Decimal("0")),
        }
        for row in rows
    ]


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
    ).aggregate(
        amount=Sum("price"),
        count=Count("id"),
    )
    return {
        "amount": row["amount"] or Decimal("0.00"),
        "count": row["count"] or 0,
    }


def _decimal_to_float(value):
    return round(float(value), 2)
