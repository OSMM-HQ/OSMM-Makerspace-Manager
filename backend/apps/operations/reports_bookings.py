from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count, DurationField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Greatest, Least
from django.utils import timezone

from apps.bookings.models import BookableSpace, Booking
from apps.operations.report_registry import ReportResult
from apps.operations.report_scope import scoped_ids


FIELDS = (
    "space_id", "space_name", "kind", "is_active", "booked", "completed",
    "no_show", "cancelled", "upcoming", "reserved_hours", "completed_hours",
    "window_hours", "reservation_utilization_percent", "no_show_rate_percent",
)
NON_CANCELLED = (
    Booking.Status.CONFIRMED,
    Booking.Status.COMPLETED,
    Booking.Status.NO_SHOW,
)
CENT = Decimal("0.01")


def build_booking_utilization(makerspace_id, *, limit=None, date_range=None):
    aggregate = makerspace_id is None
    now = timezone.now()
    overlap = Q()
    start = end = None
    if date_range:
        start, end = date_range
        if start is not None:
            overlap &= Q(bookings__ends_at__gt=start)
        if end is not None:
            overlap &= Q(bookings__starts_at__lt=end)
    clipped_start = Greatest(F("bookings__starts_at"), Value(start)) if start else F("bookings__starts_at")
    clipped_end = Least(F("bookings__ends_at"), Value(end)) if end else F("bookings__ends_at")
    duration = ExpressionWrapper(clipped_end - clipped_start, output_field=DurationField())
    qs = BookableSpace.objects.filter(
        makerspace_id__in=scoped_ids(makerspace_id, "bookings")
    ).values("id", "makerspace_id", "name", "kind", "is_active").annotate(
        booked_count=Count("bookings", filter=overlap & Q(bookings__status=Booking.Status.CONFIRMED)),
        completed_count=Count("bookings", filter=overlap & Q(bookings__status=Booking.Status.COMPLETED)),
        no_show_count=Count("bookings", filter=overlap & Q(bookings__status=Booking.Status.NO_SHOW)),
        cancelled_count=Count("bookings", filter=overlap & Q(bookings__status=Booking.Status.CANCELLED)),
        upcoming_count=Count("bookings", filter=overlap & Q(bookings__status=Booking.Status.CONFIRMED, bookings__starts_at__gte=now)),
        reserved_duration=Sum(duration, filter=overlap & Q(bookings__status__in=NON_CANCELLED)),
        completed_duration=Sum(duration, filter=overlap & Q(bookings__status=Booking.Status.COMPLETED)),
    )
    rows = list(qs)
    window_hours = _hours(end - start) if start and end else None
    records = []
    for row in rows:
        reserved = _hours(row["reserved_duration"] or timedelta())
        completed = _hours(row["completed_duration"] or timedelta())
        terminal = row["completed_count"] + row["no_show_count"]
        record = {
            "space_id": row["id"], "space_name": row["name"],
            "kind": row["kind"], "is_active": row["is_active"],
            "booked": row["booked_count"], "completed": row["completed_count"],
            "no_show": row["no_show_count"], "cancelled": row["cancelled_count"],
            "upcoming": row["upcoming_count"], "reserved_hours": reserved,
            "completed_hours": completed, "window_hours": window_hours,
            "reservation_utilization_percent": round(float(reserved / window_hours * 100), 2) if window_hours else None,
            "no_show_rate_percent": round(row["no_show_count"] / terminal * 100, 2) if terminal else None,
        }
        if aggregate:
            record["makerspace_id"] = row["makerspace_id"]
        records.append(record)
    records.sort(key=lambda row: _sort_key(row, aggregate))
    if limit is not None:
        records = records[:limit]
    fields = (("makerspace_id",) + FIELDS) if aggregate else FIELDS
    return ReportResult(fields, records)


def _hours(value):
    micros = ((value.days * 86400 + value.seconds) * 1_000_000) + value.microseconds
    return (Decimal(micros) / Decimal(3_600_000_000)).quantize(CENT, rounding=ROUND_HALF_UP)


def _sort_key(row, aggregate):
    prefix = (row["makerspace_id"],) if aggregate else ()
    return (*prefix, -row["reserved_hours"], row["space_name"], row["space_id"])
