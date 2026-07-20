"""Canonical member-safe ranks for the machine-service waiting queue."""

from django.db.models import Case, Count, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce

from apps.machines.models import MachineServiceRequest


WAITING_STATUSES = (
    MachineServiceRequest.Status.PENDING,
    MachineServiceRequest.Status.ACCEPTED,
)


def queue_positions_for(requests) -> dict[int, int]:
    """Return positions within each bucket or pooled queue, accepted work first."""
    targets = [row for row in requests if row.status in WAITING_STATUSES]
    if not targets:
        return {}
    positions = {}
    for bucket_id, queue_id in {(row.bucket_id, row.queue_id) for row in targets}:
        scope = {"bucket_id": bucket_id} if bucket_id else {"queue_id": queue_id}
        ranked = MachineServiceRequest.objects.filter(**scope, status__in=WAITING_STATUSES).order_by(
            Case(When(status=MachineServiceRequest.Status.ACCEPTED, then=Value(0)), default=Value(1)),
            "created_at", "id",
        )
        positions.update({row.pk: index for index, row in enumerate(ranked, 1)})
    return {row.pk: positions[row.pk] for row in targets}


def queue_counts_for(requests) -> dict[int, dict]:
    """Return member-safe waiting counts using the legacy print queue contract."""
    targets = [row for row in requests if row.status in WAITING_STATUSES]
    counts = {}
    for row in targets:
        scope = {"bucket_id": row.bucket_id} if row.bucket_id else {"queue_id": row.queue_id}
        waiting = MachineServiceRequest.objects.filter(**scope, status__in=WAITING_STATUSES)
        earlier = Q(created_at__lt=row.created_at) | Q(created_at=row.created_at, id__lt=row.id)
        if row.status == MachineServiceRequest.Status.ACCEPTED:
            approved_ahead = waiting.filter(status=MachineServiceRequest.Status.ACCEPTED).filter(earlier).count()
            awaiting_review_ahead = 0
        else:
            approved_ahead = waiting.filter(status=MachineServiceRequest.Status.ACCEPTED).count()
            awaiting_review_ahead = waiting.filter(status=MachineServiceRequest.Status.PENDING).filter(earlier).count()
        counts[row.pk] = {
            "position": approved_ahead + awaiting_review_ahead + 1,
            "approved_ahead": approved_ahead,
            "awaiting_review_ahead": awaiting_review_ahead,
        }
    return counts
