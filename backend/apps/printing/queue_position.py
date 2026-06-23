"""Public print queue ranks.

Accepted requests rank ahead of pending requests; ties are ordered by created_at and
then id. A request's position is everything ahead of it plus one. Counts are computed
with SQL counts for the target requests rather than loading the whole waiting queue.
"""

from django.db.models import Q

from apps.printing.models import PrintRequest

WAITING_STATUSES = (PrintRequest.Status.PENDING, PrintRequest.Status.ACCEPTED)


def queue_counts_for(makerspace, requests) -> dict[int, dict]:
    targets = [request for request in requests if request.status in WAITING_STATUSES]
    if not targets:
        return {}
    return {request.id: _counts_for_request(makerspace.id, request) for request in targets}


def _counts_for_request(makerspace_id, request):
    accepted_ahead = _waiting_queryset(makerspace_id).filter(
        status=PrintRequest.Status.ACCEPTED
    )
    pending_ahead = _waiting_queryset(makerspace_id).filter(
        status=PrintRequest.Status.PENDING
    )
    if request.status == PrintRequest.Status.ACCEPTED:
        accepted_ahead = accepted_ahead.filter(_before(request))
        pending_ahead = pending_ahead.none()
    else:
        pending_ahead = pending_ahead.filter(_before(request))
    approved = accepted_ahead.count()
    pending = pending_ahead.count()
    return {
        "position": approved + pending + 1,
        "approved_ahead": approved,
        "awaiting_review_ahead": pending,
    }


def _waiting_queryset(makerspace_id):
    return PrintRequest.objects.filter(
        bucket__makerspace_id=makerspace_id,
        status__in=WAITING_STATUSES,
    )


def _before(request):
    return Q(created_at__lt=request.created_at) | Q(
        created_at=request.created_at,
        id__lt=request.id,
    )
