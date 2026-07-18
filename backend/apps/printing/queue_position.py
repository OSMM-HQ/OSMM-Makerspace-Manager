"""Public print queue ranks.

Accepted requests rank ahead of pending requests; ties are ordered by created_at and
then id. A request's position is everything ahead of it plus one. Counts are computed
with SQL counts for the target requests rather than loading the whole waiting queue.
"""

from django.db.models import Case, Count, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce

from apps.printing.models import PrintRequest

WAITING_STATUSES = (PrintRequest.Status.PENDING, PrintRequest.Status.ACCEPTED)


def queue_counts_for(makerspace, requests) -> dict[int, dict]:
    targets = [request for request in requests if request.status in WAITING_STATUSES]
    if not targets:
        return {}
    before = Q(created_at__lt=OuterRef("created_at")) | Q(
        created_at=OuterRef("created_at"), id__lt=OuterRef("id")
    )
    waiting = PrintRequest.objects.filter(
        bucket__makerspace_id=OuterRef("bucket__makerspace_id"),
        status__in=WAITING_STATUSES,
    ).filter(before).order_by()
    accepted_total = PrintRequest.objects.filter(
        bucket__makerspace_id=OuterRef("bucket__makerspace_id"),
        status=PrintRequest.Status.ACCEPTED,
    ).values(
        "bucket__makerspace_id"
    ).annotate(total=Count("id")).values("total")[:1]
    accepted_before = waiting.filter(status=PrintRequest.Status.ACCEPTED).values(
        "bucket__makerspace_id"
    ).annotate(total=Count("id")).values("total")[:1]
    pending_before = waiting.filter(status=PrintRequest.Status.PENDING).values(
        "bucket__makerspace_id"
    ).annotate(total=Count("id")).values("total")[:1]
    rows = PrintRequest.objects.filter(pk__in=[request.id for request in targets]).annotate(
        accepted_ahead=Case(
            When(
                status=PrintRequest.Status.ACCEPTED,
                then=Coalesce(Subquery(accepted_before, output_field=IntegerField()), Value(0)),
            ),
            default=Coalesce(Subquery(accepted_total, output_field=IntegerField()), Value(0)),
            output_field=IntegerField(),
        ),
        pending_ahead=Case(
            When(
                status=PrintRequest.Status.PENDING,
                then=Coalesce(Subquery(pending_before, output_field=IntegerField()), Value(0)),
            ),
            default=Value(0),
            output_field=IntegerField(),
        ),
    )
    counts = {}
    for request in rows:
        pending_ahead = request.pending_ahead if request.status == PrintRequest.Status.PENDING else 0
        counts[request.id] = {
            "position": request.accepted_ahead + pending_ahead + 1,
            "approved_ahead": request.accepted_ahead,
            "awaiting_review_ahead": pending_ahead,
        }
    return counts
