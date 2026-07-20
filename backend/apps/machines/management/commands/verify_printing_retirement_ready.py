from django.core.management.base import BaseCommand, CommandError

from apps.machines.printing_retirement import unready_makerspaces


class Command(BaseCommand):
    help = "Verify every printing-enabled or legacy-print-data-owning tenant is kernel-authoritative."

    def handle(self, *args, **options):
        unready = list(unready_makerspaces())
        if unready:
            details = ", ".join(f"{row.pk}:{row.slug}" for row in unready)
            raise CommandError(f"Legacy printing retirement is not ready; unflipped makerspaces: {details}")
        self.stdout.write(self.style.SUCCESS("Legacy printing retirement is ready."))