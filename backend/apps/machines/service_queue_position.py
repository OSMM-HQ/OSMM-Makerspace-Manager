"""Canonical member-safe ranks for the machine-service waiting queue."""

from django.db.models import Case, Count, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce

from apps.machines.models import MachineServiceRequest


WAITING_STATUSES = (
    MachineServiceRequest.Status.PENDING,
    MachineServiceRequest.Status.ACCEPTED,
)


def queue_positions_for(requests) -> dict[int, int]:
    """Return positions within each service bucket, with accepted work first."""
    targets = [row for row in requests if row.status in WAITING_STATUSES]
    if not targets:
        return {}
    before = Q(created_at__lt=OuterRef("created_at")) | Q(
        created_at=OuterRef("created_at"), id__lt=OuterRef("id")
    )
    waiting = MachineServiceRequest.objects.filter(
        bucket_id=OuterRef("bucket_id"), status__in=WAITING_STATUSES,
    ).filter(before).order_by()
    accepted_total = MachineServiceRequest.objects.filter(
        bucket_id=OuterRef("bucket_id"), status=MachineServiceRequest.Status.ACCEPTED,
    ).values("bucket_id").annotate(total=Count("id")).values("total")[:1]
    accepted_before = waiting.filter(
        status=MachineServiceRequest.Status.ACCEPTED,
    ).values("bucket_id").annotate(total=Count("id")).values("total")[:1]
    pending_before = waiting.filter(
        status=MachineServiceRequest.Status.PENDING,
    ).values("bucket_id").annotate(total=Count("id")).values("total")[:1]
    rows = MachineServiceRequest.objects.filter(pk__in=[row.pk for row in targets]).annotate(
        accepted_ahead=Case(
            When(
                status=MachineServiceRequest.Status.ACCEPTED,
                then=Coalesce(Subquery(accepted_before, output_field=IntegerField()), Value(0)),
            ),
            default=Coalesce(Subquery(accepted_total, output_field=IntegerField()), Value(0)),
            output_field=IntegerField(),
        ),
        pending_ahead=Case(
            When(
                status=MachineServiceRequest.Status.PENDING,
                then=Coalesce(Subquery(pending_before, output_field=IntegerField()), Value(0)),
            ),
            default=Value(0),
            output_field=IntegerField(),
        ),
    )
    return {row.pk: row.accepted_ahead + row.pending_ahead + 1 for row in rows}
