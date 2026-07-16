from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce

from apps.machines.models import Machine
from apps.operations.report_registry import ReportResult
from apps.operations.report_scope import scoped_ids


FIELDS = (
    "machine_id", "machine_name", "machine_type", "is_active",
    "usage_entries", "usage_hours",
)


def build_machine_usage(makerspace_id, *, limit=None, date_range=None):
    aggregate = makerspace_id is None
    period = _period_q("usage_entries__created_at", date_range)
    queryset = (
        Machine.objects.filter(makerspace_id__in=scoped_ids(makerspace_id, "machines"))
        .values("id", "makerspace_id", "name", "machine_type__name", "is_active")
        .annotate(
            entry_count=Count("usage_entries", filter=period),
            hours=Coalesce(
                Sum("usage_entries__hours", filter=period),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=20, decimal_places=2),
            ),
        )
    )
    ordering = ("makerspace_id", "-hours", "name", "id") if aggregate else ("-hours", "name", "id")
    rows = list(queryset.order_by(*ordering)[:limit] if limit is not None else queryset.order_by(*ordering))
    fields = (("makerspace_id",) + FIELDS) if aggregate else FIELDS
    records = []
    for row in rows:
        record = {
            "machine_id": row["id"],
            "machine_name": row["name"],
            "machine_type": row["machine_type__name"],
            "is_active": row["is_active"],
            "usage_entries": row["entry_count"],
            "usage_hours": row["hours"] or Decimal("0.00"),
        }
        if aggregate:
            record["makerspace_id"] = row["makerspace_id"]
        records.append(record)
    return ReportResult(fields, records)


def _period_q(field, date_range):
    query = Q()
    if date_range:
        start, end = date_range
        if start is not None:
            query &= Q(**{f"{field}__gte": start})
        if end is not None:
            query &= Q(**{f"{field}__lt": end})
    return query
