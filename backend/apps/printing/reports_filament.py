from decimal import Decimal

from django.db.models import Sum

from apps.printing.models import FilamentAdjustment, PrintRequest

COMPLETED_STATUSES = [PrintRequest.Status.COMPLETED, PrintRequest.Status.COLLECTED]


def filament_by_brand(spools, date_range=None):
    totals = {}
    for spool in spools.only("brand", "initial_weight_grams", "remaining_weight_grams"):
        brand = (spool.brand or "").strip() or "Unbranded"
        entry = totals.setdefault(brand, {"grams": Decimal("0"), "spools": 0})
        entry["grams"] += spool_grams_used(spool, date_range=date_range)
        entry["spools"] += 1
    rows = [
        {"brand": brand, "grams_used": decimal_to_float(data["grams"]), "spools": data["spools"]}
        for brand, data in totals.items()
    ]
    rows.sort(key=lambda row: row["grams_used"], reverse=True)
    return rows


def filament_used(spools, include_makerspace, date_range=None):
    data = []
    for spool in spools.order_by("makerspace_id", "material", "color", "id"):
        item = {
            "spool_id": spool.id,
            "material": spool.material,
            "color": spool.color,
            "grams_used": decimal_to_float(spool_grams_used(spool, date_range=date_range)),
            "remaining_grams": decimal_to_float(spool.remaining_weight_grams),
        }
        if include_makerspace:
            item["makerspace_id"] = spool.makerspace_id
        data.append(item)
    return data


def total_spool_grams_used(spools, date_range=None):
    total = Decimal("0")
    for spool in spools.only("initial_weight_grams", "remaining_weight_grams"):
        total += spool_grams_used(spool, date_range=date_range)
    return decimal_to_float(total)


def spool_grams_used(spool, date_range=None):
    # P10b ledger cutover: post-ledger spools report net usage from immutable
    # FilamentAdjustment rows. Spools created/used before this ledger have no
    # adjustment rows, so they intentionally fall back to the old state-derived
    # initial-minus-remaining math instead of needing a feature flag or backfill.
    if not FilamentAdjustment.objects.filter(filament_spool=spool).exists():
        return max(spool.initial_weight_grams - spool.remaining_weight_grams, Decimal("0"))

    qs = FilamentAdjustment.objects.filter(filament_spool=spool)
    if date_range:
        start, end = date_range
        if start is not None:
            qs = qs.filter(created_at__gte=start)
        if end is not None:
            qs = qs.filter(created_at__lt=end)
    balance = qs.aggregate(total=Sum("grams"))["total"] or Decimal("0")
    return max(-balance, Decimal("0"))


def estimated_filament_by_period(requests, trunc, period_format):
    rows = (
        requests.filter(
            status__in=COMPLETED_STATUSES,
            completed_at__isnull=False,
        )
        .annotate(period=trunc("completed_at"))
        .values("period", "run_planned_filament_grams", "estimated_filament_grams")
        .order_by("period")
    )
    totals = {}
    for row in rows:
        grams = row["run_planned_filament_grams"]
        if grams is None:
            grams = row["estimated_filament_grams"] or Decimal("0")
        totals[row["period"]] = totals.get(row["period"], Decimal("0")) + grams
    return [
        {
            "period": period.strftime(period_format),
            "grams": decimal_to_float(grams),
        }
        for period, grams in sorted(totals.items())
    ]

def decimal_to_float(value):
    return round(float(value), 2)


