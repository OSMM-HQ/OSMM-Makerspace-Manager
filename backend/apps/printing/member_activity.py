from apps.printing.models import PrintRequest
from apps.printing.public_serializers import PublicPrintStatusSerializer
from apps.printing.queue_position import queue_counts_for


def member_print_requests(makerspace, member, *, limit=None):
    requests = PrintRequest.objects.filter(
        requester=member,
        bucket__makerspace=makerspace,
    ).select_related("bucket__makerspace").order_by("-created_at", "-id")
    return requests[:limit] if limit is not None else requests


def member_print_activity(makerspace, member, *, limit=None):
    requests = list(member_print_requests(makerspace, member, limit=limit))
    return PublicPrintStatusSerializer(
        requests,
        many=True,
        context={"queue_counts": queue_counts_for(makerspace, requests)},
    ).data
