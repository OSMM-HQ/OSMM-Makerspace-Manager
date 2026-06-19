from django.core.management.base import BaseCommand

from apps.hardware_requests.services_return_reminders import run_return_reminders


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
        result = run_return_reminders(limit=options["limit"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Return reminders sent: {result['sent']}; skipped: {result['skipped']}"
            )
        )
