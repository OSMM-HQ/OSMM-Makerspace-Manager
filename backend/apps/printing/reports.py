from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum
from django.db.models.functions import Coalesce, TruncDay, TruncHour, TruncMonth
from django.conf import settings

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
    """Build from the source authoritative for each makerspace during B4."""
    from apps.machines.printing_cutover import kernel_is_authoritative
    from apps.printing.reports_kernel import build_kernel_printing_report

    if makerspace_id is not None:
        from apps.makerspaces.models import Makerspace

        makerspace = Makerspace.objects.get(pk=makerspace_id)
        if kernel_is_authoritative(makerspace):
            return build_kernel_printing_report(
                makerspace_id, include_makerspace=include_makerspace, date_range=date_range,
            )
        return _build_legacy_printing_report(
            makerspace_id, include_makerspace=include_makerspace, date_range=date_range,
        )

    # Preserve the existing SQL report path whenever every eligible tenant is
    # still legacy.  Mixed global reports are composed from one authoritative
    # per-tenant projection, so imported provenance is never double counted.
    from apps.makerspaces.models import Makerspace

    excluded = rbac.superadmin_hidden_makerspace_ids() | rbac.archived_makerspace_ids()
    spaces = Makerspace.objects.exclude(pk__in=excluded).order_by("pk")
    if not spaces.filter(printing_cutover_state__kernel_authoritative_at__isnull=False).exists():
        return _build_legacy_printing_report(
            include_makerspace=include_makerspace, date_range=date_range,
        )
    reports = [
        build_printing_report(space.pk, include_makerspace=True, date_range=date_range)
        for space in spaces
    ]
    return _merge_tenant_reports(reports, include_makerspace=include_makerspace)


def _build_legacy_printing_report(makerspace_id=None, *, include_makerspace=False, date_range=None):
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
        "filament_used": filament_used(spools, include_makerspace, date_range=date_range),
        "filament_by_brand": filament_by_brand(spools, date_range=date_range),
        "top_requesters": _top_requesters(completed_period, include_makerspace),
        "total_grams_used": total_spool_grams_used(spools, date_range=date_range),
        "payments": _payments(completed_period),
        "filament_estimated_by_period": {
            "by_month": estimated_filament_by_period(completed_period, TruncMonth, "%Y-%m"),
            "by_day": estimated_filament_by_period(completed_period, TruncDay, "%Y-%m-%d"),
            "by_hour": estimated_filament_by_period(completed_period, TruncHour, "%Y-%m-%d %H:00"),
        },
    }


def _merge_tenant_reports(reports, *, include_makerspace):
    totals = {key: 0 for key in ("total_requests", *STATUS_KEYS.values())}
    payments = {"paid_amount": Decimal("0.00"), "paid_count": 0, "outstanding_amount": Decimal("0.00"), "outstanding_count": 0}
    rows = {key: [] for key in ("printer_hours", "printer_outcomes", "filament_used", "top_requesters")}
    brands, periods = {}, {key: {} for key in ("by_month", "by_day", "by_hour")}
    total_grams = 0.0
    for report in reports:
        for key in totals:
            totals[key] += report["totals"][key]
        for key in payments:
            payments[key] += report["payments"][key]
        total_grams += report["total_grams_used"]
        for key in rows:
            rows[key].extend(report[key])
        for brand in report["filament_by_brand"]:
            row = brands.setdefault(brand["brand"], {"brand": brand["brand"], "grams_used": 0.0, "spools": 0})
            row["grams_used"] += brand["grams_used"]
            row["spools"] += brand["spools"]
        for grain, entries in report["filament_estimated_by_period"].items():
            for entry in entries:
                periods[grain][entry["period"]] = periods[grain].get(entry["period"], 0.0) + entry["grams"]
    if not include_makerspace:
        for key in rows:
            for row in rows[key]:
                row.pop("makerspace_id", None)
    return {
        "totals": totals,
        "printer_hours": sorted(rows["printer_hours"], key=lambda row: (row.get("makerspace_id") or 0, row["printer_name"], row["printer_id"])),
        "printer_outcomes": sorted(rows["printer_outcomes"], key=lambda row: (row.get("makerspace_id") or 0, row["printer_name"], row["printer_id"])),
        "filament_used": rows["filament_used"],
        "filament_by_brand": sorted(brands.values(), key=lambda row: row["grams_used"], reverse=True),
        "top_requesters": rows["top_requesters"],
        "total_grams_used": round(total_grams, 2),
        "payments": payments,
        "filament_estimated_by_period": {grain: [{"period": period, "grams": grams} for period, grams in sorted(values.items())] for grain, values in periods.items()},
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
    grams = Coalesce(
        Sum(
            Coalesce(
                "run_planned_filament_grams",
                "estimated_filament_grams",
                output_field=DecimalField(max_digits=8, decimal_places=2),
            ),
            filter=grams_filter,
        ),
        Decimal("0"),
    )

    # Pull non-PII metrics only, then group mapper-exposed values in application
    # code. This deliberately keeps all DB expressions away from ciphertext.
    from apps.encryption.blind_index import canonical_email
    from apps.encryption.models import PiiBlindIndex
    generation = None
    hashes = {}
    if settings.PII_ENCRYPTION_ENABLED:
        from apps.encryption.blind_index import active_generation
        generation = active_generation()
        hashes = {(row.makerspace_id, row.object_id): bytes(row.exact_hash) for row in PiiBlindIndex.objects.filter(search_generation=generation, model_label="printing.PrintRequest", field_name="contact_email").only("makerspace_id", "object_id", "exact_hash")}
    groups = {}
    rows = requests.select_related("bucket", "requester").only("id", "bucket__makerspace_id", "requester_id", "quantity", "status", "run_planned_filament_grams", "estimated_filament_grams", "requester_name", "contact_email", "requester__username", "requester__external_checkin_user_id")
    for row in rows.iterator(chunk_size=200):
        makerspace_id = row.bucket.makerspace_id
        email = row.contact_email
        key = hashes.get((makerspace_id, row.pk)) if email and generation else None
        key = key or (makerspace_id, canonical_email(email)) if email else ("blank", makerspace_id, row.requester_id)
        bucket = groups.setdefault(key, {"makerspace_id": makerspace_id, "requester_id": row.requester_id, "names": [], "emails": [], "requests": 0, "items": 0, "grams": Decimal("0"), "user": row.requester})
        bucket["requests"] += 1
        bucket["items"] += row.quantity or 0
        if row.status in COMPLETED_STATUSES:
            bucket["grams"] += row.run_planned_filament_grams or row.estimated_filament_grams or Decimal("0")
        if row.requester_name:
            bucket["names"].append(row.requester_name.strip())
        if email:
            bucket["emails"].append(email.strip())
    data = []
    for bucket in groups.values():
        label = next((x for x in sorted(bucket["names"]) if x), None) or next((x for x in sorted(bucket["emails"]) if x), None)
        if not label:
            label = requester_label_for_user(username=bucket["user"].username, external_checkin_user_id=bucket["user"].external_checkin_user_id)
        item = {"requester_id": bucket["requester_id"], "requester": label or "Anonymous", "grams": decimal_to_float(bucket["grams"]), "requests": bucket["requests"], "items": bucket["items"]}
        if include_makerspace:
            item["makerspace_id"] = bucket["makerspace_id"]
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

