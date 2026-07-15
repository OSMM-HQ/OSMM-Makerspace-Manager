from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q, Sum

from apps.evidence.models import EvidencePhoto
from apps.inventory import public_image_storage
from apps.inventory.models import InventoryProduct
from apps.machines.models import Machine
from apps.makerspaces.models import Makerspace
from apps.printing.models import PrintPrinter, PrintRequestFile


class Command(BaseCommand):
    help = "Recompute per-makerspace managed object-storage usage from authoritative records."

    def add_arguments(self, parser):
        parser.add_argument(
            "makerspace",
            nargs="?",
            help="Optional makerspace slug or numeric ID; defaults to all active spaces.",
        )

    def handle(self, *args, **options):
        selector = options["makerspace"]
        makerspaces = Makerspace.objects.all()
        if selector:
            lookup = Q(slug=selector)
            if selector.isdigit():
                lookup |= Q(pk=int(selector))
            makerspaces = makerspaces.filter(lookup)
            if not makerspaces.exists():
                raise CommandError(f"Makerspace {selector!r} was not found.")
        else:
            makerspaces = makerspaces.filter(archived_at__isnull=True)

        for makerspace in makerspaces.order_by("pk"):
            evidence_bytes = (
                EvidencePhoto.objects.filter(
                    makerspace=makerspace,
                    size_bytes__isnull=False,
                ).aggregate(total=Sum("size_bytes"))["total"]
                or 0
            )
            print_bytes = (
                PrintRequestFile.objects.filter(
                    print_request__bucket__makerspace=makerspace
                ).aggregate(total=Sum("size_bytes"))["total"]
                or 0
            )
            public_bytes = sum(
                public_image_storage.object_size(key) or 0
                for key in self._public_image_keys(makerspace)
            )
            total = evidence_bytes + print_bytes + public_bytes
            makerspace.storage_bytes_used = total
            makerspace.save(update_fields=["storage_bytes_used"])
            self.stdout.write(
                self.style.SUCCESS(
                    f"{makerspace.slug}: evidence={evidence_bytes} bytes, "
                    f"print={print_bytes} bytes, public_images={public_bytes} bytes, "
                    f"total={total} bytes"
                )
            )

    @staticmethod
    def _public_image_keys(makerspace):
        keys = {
            makerspace.logo_key,
            makerspace.cover_image_key,
            *InventoryProduct.objects.filter(makerspace=makerspace).values_list(
                "image_key", flat=True
            ),
            *Machine.objects.filter(makerspace=makerspace).values_list(
                "image_key", flat=True
            ),
            *PrintPrinter.objects.filter(makerspace=makerspace).values_list(
                "image_key", flat=True
            ),
        }
        keys.discard("")
        keys.discard(None)
        return keys
