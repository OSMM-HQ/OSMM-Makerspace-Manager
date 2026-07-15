from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.evidence import storage as evidence_storage
from apps.evidence.models import EvidencePhoto
from apps.inventory import public_image_storage
from apps.inventory.models import InventoryProduct
from apps.machines import storage as machine_storage
from apps.machines.models import Machine, MachineDocument
from apps.makerspaces.models import Makerspace
from apps.printing import storage as printing_storage
from apps.printing.models import PrintPrinter, PrintRequestFile
from apps.procurement import storage as procurement_storage
from apps.procurement.models import ToBuyReceipt
from apps.warranty import storage as warranty_storage
from apps.warranty.models import WarrantyDocument


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
            evidence_bytes = self._sum_observed_sizes(
                EvidencePhoto.objects.filter(makerspace=makerspace).values_list(
                    "object_key", "size_bytes"
                ),
                evidence_storage.object_size,
                fallback_to_recorded=True,
            )
            print_bytes = self._sum_observed_sizes(
                PrintRequestFile.objects.filter(
                    print_request__bucket__makerspace=makerspace
                ).values_list("object_key", "size_bytes"),
                printing_storage.print_object_size,
                fallback_to_recorded=True,
            )
            public_bytes = self._sum_observed_sizes(
                ((key, None) for key in self._public_image_keys(makerspace)),
                public_image_storage.object_size,
            )
            machine_document_bytes = self._sum_observed_sizes(
                (
                    (key, None)
                    for key in MachineDocument.objects.filter(
                        machine__makerspace=makerspace
                    ).values_list("object_key", flat=True)
                ),
                machine_storage.object_size,
            )
            warranty_document_bytes = self._sum_observed_sizes(
                (
                    (key, None)
                    for key in WarrantyDocument.objects.filter(
                        warranty__makerspace=makerspace
                    ).values_list("object_key", flat=True)
                ),
                warranty_storage.object_size,
            )
            receipt_bytes = self._sum_observed_sizes(
                (
                    (key, None)
                    for key in ToBuyReceipt.objects.filter(
                        to_buy_item__makerspace=makerspace
                    ).values_list("object_key", flat=True)
                ),
                procurement_storage.object_size,
            )
            total = (
                evidence_bytes
                + print_bytes
                + public_bytes
                + machine_document_bytes
                + warranty_document_bytes
                + receipt_bytes
            )
            makerspace.storage_bytes_used = total
            makerspace.save(update_fields=["storage_bytes_used"])
            self.stdout.write(
                self.style.SUCCESS(
                    f"{makerspace.slug}: evidence={evidence_bytes} bytes, "
                    f"print_files={print_bytes} bytes, "
                    f"public_images={public_bytes} bytes, "
                    f"machine_documents={machine_document_bytes} bytes, "
                    f"warranty_documents={warranty_document_bytes} bytes, "
                    f"procurement_receipts={receipt_bytes} bytes, "
                    f"total={total} bytes"
                )
            )

    @staticmethod
    def _sum_observed_sizes(rows, object_size, *, fallback_to_recorded=False):
        total = 0
        for object_key, recorded_size in rows:
            if not object_key:
                continue
            try:
                observed_size = object_size(object_key)
            except Exception:
                continue
            if observed_size is None:
                observed_size = recorded_size if fallback_to_recorded else 0
            total += observed_size or 0
        return total

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
