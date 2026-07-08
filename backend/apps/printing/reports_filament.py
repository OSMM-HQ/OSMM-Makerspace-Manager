from decimal import Decimal

from apps.printing.models import PrintRequest

COMPLETED_STATUSES = [PrintRequest.Status.COMPLETED, PrintRequest.Status.COLLECTED]


def filament_by_brand(spools):
    totals = {}
    for spool in spools.only("brand", "initial_weight_grams", "remaining_weight_grams"):
        brand = (spool.brand or "").strip() or "Unbranded"
        entry = totals.setdefault(brand, {"grams": Decimal("0"), "spools": 0})
        entry["grams"] += spool_grams_used(spool)
        entry["spools"] += 1
    rows = [
        {"brand": brand, "grams_used": decimal_to_float(data["grams"]), "spools": data["spools"]}
        for brand, data in totals.items()
    ]
    rows.sort(key=lambda row: row["grams_used"], reverse=True)
    return rows


def filament_used(spools, include_makerspace):
    data = []
    for spool in spools.order_by("makerspace_id", "material", "color", "id"):
        item = {
            "spool_id": spool.id,
            "material": spool.material,
            "color": spool.color,
            "grams_used": decimal_to_float(spool_grams_used(spool)),
            "remaining_grams": decimal_to_float(spool.remaining_weight_grams),
        }
        if include_makerspace:
            item["makerspace_id"] = spool.makerspace_id
        data.append(item)
    return data


def total_spool_grams_used(spools):
    total = Decimal("0")
    for spool in spools.only("initial_weight_grams", "remaining_weight_grams"):
        total += spool_grams_used(spool)
    return decimal_to_float(total)


def spool_grams_used(spool):
    return max(spool.initial_weight_grams - spool.remaining_weight_grams, Decimal("0"))


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


