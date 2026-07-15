from django.core.management.base import BaseCommand

from apps.machines.linking import reconcile_all


class Command(BaseCommand):
    help = (
        "Link any PrintPrinter that has no generalized Machine record yet. "
        "Repairs printers the fail-safe on_commit signal could not link (e.g. a "
        "transient DB error at creation time)."
    )

    def handle(self, *args, **options):
        linked = reconcile_all()
        self.stdout.write(self.style.SUCCESS(f"Linked {linked} printer(s) to machines."))
