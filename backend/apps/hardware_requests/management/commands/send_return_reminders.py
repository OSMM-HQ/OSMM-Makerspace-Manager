from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.hardware_requests import notifications
from apps.hardware_requests.models import HardwareRequest


class Command(BaseCommand):
    help = "Send due return reminder emails for active hardware requests."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="Maximum reminders to process in this run.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        limit = max(options["limit"], 1)
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

        self.stdout.write(
            self.style.SUCCESS(
                f"Return reminders sent: {sent_count}; skipped: {skipped_count}"
            )
        )
