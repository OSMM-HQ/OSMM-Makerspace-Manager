"""Public print queue ranks.

Accepted requests rank ahead of pending requests; ties are ordered by created_at and
then id. A request's position is everything ahead of it plus one. Counts are computed
with one waiting-queue query and no per-request lookups.
"""

from apps.printing.models import PrintRequest


def queue_counts_for(makerspace, requests) -> dict[int, dict]:
    targets = [
        request
        for request in requests
        if request.status in (PrintRequest.Status.PENDING, PrintRequest.Status.ACCEPTED)
    ]
    if not targets:
        return {}

    waiting = list(
        PrintRequest.objects.filter(
            bucket__makerspace_id=makerspace.id,
            status__in=[PrintRequest.Status.PENDING, PrintRequest.Status.ACCEPTED],
        ).values_list("id", "status", "created_at")
    )
    waiting.sort(
        key=lambda row: (
            0 if row[1] == PrintRequest.Status.ACCEPTED else 1,
            row[2],
            row[0],
        )
    )

    result = {}
    target_ids = {request.id for request in targets}
    approved = 0
    pending = 0
    for rid, status, _created_at in waiting:
        if rid in target_ids:
            result[rid] = {
                "position": approved + pending + 1,
                "approved_ahead": approved,
                "awaiting_review_ahead": pending,
            }
        if status == PrintRequest.Status.ACCEPTED:
            approved += 1
        else:
            pending += 1
    return result
