from django.db.models import Case, Count, DecimalField, Q, Sum, Value, When

from apps.operations.report_registry import ReportResult
from apps.operations.report_scope import scoped_ids
from apps.payments.models import Payment

FIELDS = (
    "currency",
    "subject_type",
    "status",
    "payment_count",
    "amount_total",
    "outstanding_amount",
)


def build_payment_reconciliation(
    makerspace_id,
    *,
    limit=None,
    date_range=None,
    subject_type=None,
    status=None,
):
    aggregate = makerspace_id is None
    queryset = Payment.objects.filter(makerspace_id__in=scoped_ids(makerspace_id))
    if subject_type:
        queryset = queryset.filter(subject_type=subject_type)
    if status:
        queryset = queryset.filter(status=status)
    if date_range:
        start, end = date_range
        dated = Q()
        if start is not None:
            dated &= Q(created_at__gte=start)
        if end is not None:
            dated &= Q(created_at__lt=end)
        queryset = queryset.filter(Q(status=Payment.Status.PENDING) | dated)

    group_fields = ["makerspace_id", "currency", "subject_type", "status"]
    fields = (("makerspace_id",) + FIELDS) if aggregate else FIELDS
    money = DecimalField(max_digits=20, decimal_places=2)
    rows = (
        queryset.values(*group_fields)
        .annotate(
            payment_count=Count("pk"),
            amount_total=Sum("amount"),
            outstanding_amount=Sum(
                Case(
                    When(status=Payment.Status.PENDING, then="amount"),
                    default=Value(0),
                    output_field=money,
                )
            ),
        )
        .values(*fields)
        .order_by(*group_fields)
    )
    if limit is not None:
        rows = rows[:limit]
    return ReportResult(fields, list(rows))
