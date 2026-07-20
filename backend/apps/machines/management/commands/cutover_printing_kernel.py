"""Run the B4 forward-only import gate for one makerspace."""

from django.core.management.base import BaseCommand, CommandError

from apps.machines.printing_cutover import CutoverMismatch, backfill, flip_authority, reconcile
from apps.makerspaces.models import Makerspace


class Command(BaseCommand):
    help = "Backfill/reconcile legacy printing into the machine kernel; --flip is forward-only."

    def add_arguments(self, parser):
        parser.add_argument("--makerspace", type=int, required=True)
        parser.add_argument("--reconcile-only", action="store_true")
        parser.add_argument("--flip", action="store_true")

    def handle(self, *args, **options):
        makerspace = Makerspace.objects.filter(pk=options["makerspace"]).first()
        if makerspace is None:
            raise CommandError("Makerspace was not found.")
        try:
            result = reconcile(makerspace) if options["reconcile_only"] else backfill(makerspace)
            if options["flip"]:
                flip_authority(makerspace)
        except CutoverMismatch as exc:
            raise CommandError(f"Cutover stopped; inspect PrintingCutoverRepair: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"printing kernel reconciliation passed: {result}"))
