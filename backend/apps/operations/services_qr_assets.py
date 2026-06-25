from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit
from apps.boxes.models import Box, QrCode
from apps.inventory import availability
from apps.inventory.models import InventoryAsset, InventoryProduct, TrackingMode
from apps.operations.models import QrPrintBatch, QrPrintBatchItem


def _target_label(qr):
    if qr.target_type == QrCode.TargetType.BOX:
        return Box.objects.get(pk=qr.target_id).label
    if qr.target_type == QrCode.TargetType.ASSET:
        asset = InventoryAsset.objects.select_related("product").get(pk=qr.target_id)
        return f"{asset.product.name} - {asset.asset_tag}"
    return InventoryProduct.objects.get(pk=qr.target_id).name


def add_qr_to_batch(batch, qr, label_text="", sort_order=None):
    if qr.makerspace_id != batch.makerspace_id:
        raise ValidationError("QR code belongs to a different makerspace.")
    if sort_order is None:
        sort_order = batch.items.count()
    return QrPrintBatchItem.objects.create(
        batch=batch,
        qr_code=qr,
        label_text=label_text or _target_label(qr),
        target_type=qr.target_type,
        target_id=qr.target_id,
        sort_order=sort_order,
    )


def generate_assets_with_qr(actor, product, data):
    created = []
    with transaction.atomic():
        product = InventoryProduct.objects.select_for_update().get(pk=product.pk)
        if product.tracking_mode != TrackingMode.INDIVIDUAL:
            product.tracking_mode = TrackingMode.INDIVIDUAL
            product.save(update_fields=["tracking_mode", "updated_at"])

        batch = None
        if data.get("print_batch_id"):
            batch = QrPrintBatch.objects.get(pk=data["print_batch_id"], makerspace=product.makerspace)
        elif data.get("create_print_batch"):
            batch = QrPrintBatch.objects.create(
                makerspace=product.makerspace,
                title=f"{product.name} unit QR labels",
                created_by=actor,
            )
        serials = data.get("serial_numbers") or []
        name_prefix = data.get("name_prefix") or product.name
        existing_count = product.assets.count()

        for idx in range(data["count"]):
            next_number = existing_count + idx + 1
            asset_tag = f"{product.slug if hasattr(product, 'slug') else product.id}-{next_number:04d}"
            asset = InventoryAsset.objects.create(
                makerspace=product.makerspace,
                product=product,
                box=product.box,
                asset_tag=asset_tag,
                serial_number=serials[idx] if idx < len(serials) else "",
                notes=f"{name_prefix} #{next_number}",
            )
            qr, _ = QrCode.objects.get_or_create(
                makerspace=product.makerspace,
                target_type=QrCode.TargetType.ASSET,
                target_id=asset.id,
                status=QrCode.Status.ACTIVE,
                defaults={"created_by": actor},
            )
            if batch:
                add_qr_to_batch(batch, qr, label_text=f"{name_prefix} {next_number}")
            created.append({"asset": asset, "qr": qr})

        availability.reconcile_individual_product_from_assets(product)
        audit.record(actor, "asset_units.generated", makerspace=product.makerspace, target=product, meta={"count": data["count"]})
    return created, batch


def mark_batch_printed(actor, batch):
    with transaction.atomic():
        locked = QrPrintBatch.objects.select_for_update().get(pk=batch.pk)
        # Only a draft batch can be marked printed: block re-printing and prevent an
        # archived batch from being silently unarchived back to printed.
        if locked.status != QrPrintBatch.Status.DRAFT:
            raise ValidationError(
                f"Only draft QR print batches can be marked printed (status: {locked.status})."
            )
        locked.status = QrPrintBatch.Status.PRINTED
        locked.printed_at = timezone.now()
        locked.save(update_fields=["status", "printed_at"])
        audit.record(actor, "qr_print_batch.printed", makerspace=locked.makerspace, target=locked)
        return locked
