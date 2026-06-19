from django.db import transaction
from django.utils import timezone

from apps.hardware_requests import notifications
from apps.hardware_requests.models import HardwareRequest


def run_return_reminders(*, now=None, limit=200) -> dict:
    now = now or timezone.now()
    limit = max(int(limit), 1)
    queryset = (
        HardwareRequest.objects.select_related("makerspace", "requester")
        .filter(
            status__in=[
                HardwareRequest.Status.ISSUED,
                HardwareRequest.Status.PARTIALLY_RETURNED,
            ],
            return_due_at__lte=now,
            return_reminder_sent_at__isnull=True,
        )
        .order_by("return_due_at", "id")[:limit]
    )
    sent_count = 0
    skipped_count = 0
    for hardware_request in queryset:
        if notifications.notify_return_due(hardware_request):
            with transaction.atomic():
                updated = HardwareRequest.objects.filter(
                    pk=hardware_request.pk,
                    return_reminder_sent_at__isnull=True,
                ).update(return_reminder_sent_at=now)
            sent_count += updated
        else:
            skipped_count += 1

    return {"sent": sent_count, "skipped": skipped_count}
