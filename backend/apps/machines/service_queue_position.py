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
