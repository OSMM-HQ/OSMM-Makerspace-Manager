from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit
from apps.boxes.models import Box, QrCode
from apps.inventory.models import InventoryAsset, InventoryProduct, TrackingMode
from apps.operations.models import (
    InventoryAdjustment,
    QrPrintBatch,
    QrPrintBatchItem,
    StockTransfer,
    StockTransferLine,
    StocktakeLine,
    StocktakeSession,
)


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


def apply_stock_transfer(actor, makerspace, data):
    with transaction.atomic():
        source = _container(data.get("source_container_id"), makerspace.id)
        destination = _container(data.get("destination_container_id"), makerspace.id)
        destination_makerspace_id = data.get("destination_makerspace_id") or makerspace.id
        transfer = StockTransfer.objects.create(
            makerspace=makerspace,
            source_container=source,
            destination_container=destination,
            source_makerspace=makerspace,
            destination_makerspace_id=destination_makerspace_id,
            created_by=actor,
            reason=data["reason"],
            applied_at=timezone.now(),
        )
        for line_data in data["lines"]:
            product = None
            asset = None
            quantity = line_data.get("quantity") or 1
            if line_data.get("asset_id"):
                asset = InventoryAsset.objects.select_for_update().select_related("product").get(
                    pk=line_data["asset_id"],
                    makerspace=makerspace,
                )
                if source and asset.box_id != source.id:
                    raise ValidationError({"asset_id": "Asset is not in the source container."})
                asset.box = destination
                if line_data.get("to_status"):
                    asset.status = line_data["to_status"]
                asset.save(update_fields=["box", "status", "updated_at"])
                product = asset.product
            else:
                product = InventoryProduct.objects.select_for_update().get(
                    pk=line_data["product_id"],
                    makerspace=makerspace,
                )
                if source and product.box_id != source.id:
                    raise ValidationError({"product_id": "Product is not in the source container."})
                if quantity > product.total_quantity:
                    raise ValidationError({"quantity": "Cannot transfer more than total stock."})
                product.box = destination
                product.save(update_fields=["box", "updated_at"])
            StockTransferLine.objects.create(
                transfer=transfer,
                product=None if asset else product,
                asset=asset,
                quantity=quantity,
                from_status=line_data.get("from_status", ""),
                to_status=line_data.get("to_status", ""),
                notes=line_data.get("notes", ""),
            )
            InventoryAdjustment.objects.create(
                makerspace=makerspace,
                transfer=transfer,
                product=None if asset else product,
                asset=asset,
                reason=data["reason"],
                created_by=actor,
            )
        audit.record(actor, "stock_transfer.applied", makerspace=makerspace, target=transfer)
        return transfer


def create_stocktake(actor, makerspace, data):
    container = _container(data.get("container_id"), makerspace.id)
    stocktake = StocktakeSession.objects.create(
        makerspace=makerspace,
        container=container,
        started_by=actor,
        notes=data.get("notes", ""),
    )
    audit.record(actor, "stocktake.created", makerspace=makerspace, target=stocktake)
    return stocktake


def add_stocktake_line(actor, stocktake, data):
    if stocktake.status not in {StocktakeSession.Status.DRAFT, StocktakeSession.Status.COUNTING}:
        raise ValidationError("Cannot add count lines after stocktake is completed.")
    product = None
    asset = None
    expected = 0
    if data.get("asset_id"):
        asset = InventoryAsset.objects.get(pk=data["asset_id"], makerspace=stocktake.makerspace)
        expected = 1 if asset.status == InventoryAsset.Status.AVAILABLE else 0
    else:
        product = InventoryProduct.objects.get(pk=data["product_id"], makerspace=stocktake.makerspace)
        expected = product.available_quantity
    container = _container(data.get("container_id"), stocktake.makerspace_id)
    counted = data["counted_quantity"]
    line = StocktakeLine.objects.create(
        stocktake=stocktake,
        product=product,
        asset=asset,
        container=container,
        expected_quantity=expected,
        counted_quantity=counted,
        variance_quantity=counted - expected,
        condition=data.get("condition") or StocktakeLine.Condition.AVAILABLE,
        notes=data.get("notes", ""),
    )
    audit.record(actor, "stocktake.line_counted", makerspace=stocktake.makerspace, target=stocktake, meta={"line_id": line.id})
    return line


def complete_stocktake(actor, stocktake):
    if stocktake.status != StocktakeSession.Status.COUNTING:
        raise ValidationError("Only counting stocktakes can be completed.")
    stocktake.status = StocktakeSession.Status.COMPLETED
    stocktake.completed_at = timezone.now()
    stocktake.save(update_fields=["status", "completed_at"])
    audit.record(actor, "stocktake.completed", makerspace=stocktake.makerspace, target=stocktake)
    return stocktake


def approve_stocktake(actor, stocktake):
    if stocktake.status != StocktakeSession.Status.COMPLETED:
        raise ValidationError("Only completed stocktakes can be approved.")
    stocktake.status = StocktakeSession.Status.APPROVED
    stocktake.approved_by = actor
    stocktake.approved_at = timezone.now()
    stocktake.save(update_fields=["status", "approved_by", "approved_at"])
    audit.record(actor, "stocktake.approved", makerspace=stocktake.makerspace, target=stocktake)
    return stocktake


def apply_stocktake_adjustments(actor, stocktake):
    if stocktake.status != StocktakeSession.Status.APPROVED:
        raise ValidationError("Only approved stocktakes can be applied.")
    with transaction.atomic():
        locked = StocktakeSession.objects.select_for_update().get(pk=stocktake.pk)
        for line in locked.lines.select_related("product", "asset"):
            if line.variance_quantity == 0:
                continue
            if line.asset_id:
                _apply_asset_line(line)
            else:
                _apply_product_line(line)
            InventoryAdjustment.objects.create(
                makerspace=locked.makerspace,
                stocktake=locked,
                product=line.product,
                asset=line.asset,
                delta_available=line.variance_quantity if line.condition == StocktakeLine.Condition.AVAILABLE else 0,
                delta_damaged=line.variance_quantity if line.condition == StocktakeLine.Condition.DAMAGED else 0,
                delta_lost=line.variance_quantity if line.condition == StocktakeLine.Condition.LOST else 0,
                reason=f"Stocktake #{locked.id}: {line.notes}".strip(),
                created_by=actor,
            )
        locked.status = StocktakeSession.Status.APPLIED
        locked.save(update_fields=["status"])
        audit.record(actor, "stocktake.adjustments_applied", makerspace=locked.makerspace, target=locked)
        return locked


def generate_assets_with_qr(actor, product, data):
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
    created = []
    with transaction.atomic():
        for idx in range(data["count"]):
            next_number = product.assets.count() + 1
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
                add_qr_to_batch(batch, qr, label_text=f"{product.name} - {asset.asset_tag}")
            created.append({"asset": asset, "qr": qr})
        audit.record(actor, "asset_units.generated", makerspace=product.makerspace, target=product, meta={"count": data["count"]})
    return created, batch


def _container(container_id, makerspace_id):
    if not container_id:
        return None
    return Box.objects.get(pk=container_id, makerspace_id=makerspace_id)


def _apply_product_line(line):
    product = InventoryProduct.objects.select_for_update().get(pk=line.product_id)
    if line.condition == StocktakeLine.Condition.AVAILABLE:
        new_available = product.available_quantity + line.variance_quantity
        if new_available < 0:
            raise ValidationError("Stocktake adjustment would make available stock negative.")
        product.available_quantity = new_available
    elif line.condition == StocktakeLine.Condition.DAMAGED:
        product.damaged_quantity = max(0, product.damaged_quantity + line.variance_quantity)
    elif line.condition == StocktakeLine.Condition.LOST:
        product.lost_quantity = max(0, product.lost_quantity + line.variance_quantity)
    product.total_quantity = (
        product.available_quantity
        + product.reserved_quantity
        + product.issued_quantity
        + product.damaged_quantity
        + product.lost_quantity
    )
    product.save()


def _apply_asset_line(line):
    asset = InventoryAsset.objects.select_for_update().get(pk=line.asset_id)
    if line.counted_quantity == 0:
        asset.status = InventoryAsset.Status.LOST
    elif line.condition == StocktakeLine.Condition.DAMAGED:
        asset.status = InventoryAsset.Status.DAMAGED
    else:
        asset.status = InventoryAsset.Status.AVAILABLE
    asset.save(update_fields=["status", "updated_at"])
