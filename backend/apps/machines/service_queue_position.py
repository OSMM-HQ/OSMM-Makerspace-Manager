"""Canonical member-safe ranks for the machine-service waiting queue."""

from collections import defaultdict

from django.db.models import Case, Q, Value, When

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
    for key in _scope_keys(targets):
        ranked = _waiting_for_scope(key)
        positions.update({row.pk: index for index, row in enumerate(ranked, 1)})
    return {row.pk: positions[row.pk] for row in targets}


def queue_counts_for(requests) -> dict[int, dict]:
    """Return queue counts with a bounded query count for a list of requests."""
    targets = [row for row in requests if row.status in WAITING_STATUSES]
    if not targets:
        return {}
    ranked_by_scope = _waiting_rows(_scope_keys(targets))
    counts = {}
    for row in targets:
        ranked = ranked_by_scope[_scope_key(row)]
        accepted = 0
        pending = 0
        for candidate in ranked:
            if candidate.pk == row.pk:
                break
            if candidate.status == MachineServiceRequest.Status.ACCEPTED:
                accepted += 1
            else:
                pending += 1
        counts[row.pk] = {
            "position": accepted + pending + 1,
            "approved_ahead": accepted,
            "awaiting_review_ahead": pending if row.status == MachineServiceRequest.Status.PENDING else 0,
        }
    return counts


def _scope_key(row):
    return ("bucket", row.bucket_id) if row.bucket_id else ("queue", row.queue_id)


def _scope_keys(rows):
    return {_scope_key(row) for row in rows}


def _waiting_for_scope(key):
    field, value = key
    return list(MachineServiceRequest.objects.filter(
        **{f"{field}_id": value}, status__in=WAITING_STATUSES,
    ).order_by(_priority(), "created_at", "id"))


def _waiting_rows(keys):
    queue_ids = [value for field, value in keys if field == "queue"]
    bucket_ids = [value for field, value in keys if field == "bucket"]
    rows = MachineServiceRequest.objects.filter(status__in=WAITING_STATUSES).filter(
        Q(queue_id__in=queue_ids) | Q(bucket_id__in=bucket_ids),
    ).order_by(_priority(), "created_at", "id")
    grouped = defaultdict(list)
    for row in rows:
        grouped[_scope_key(row)].append(row)
    return grouped


def _priority():
    return Case(
        When(status=MachineServiceRequest.Status.ACCEPTED, then=Value(0)),
        default=Value(1),
    )