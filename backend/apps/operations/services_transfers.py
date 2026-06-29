from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit
from apps.inventory import availability
from apps.inventory.models import InventoryAsset, InventoryProduct, TrackingMode
from apps.makerspaces.models import Makerspace
from apps.operations.models import InventoryAdjustment, StockTransfer, StockTransferLine
from apps.operations.services_shared import _container
from apps.operations.services_transfer_splits import move_quantity_stock


def apply_stock_transfer(actor, makerspace, data):
    with transaction.atomic():
        destination_makerspace_id = data.get("destination_makerspace_id") or makerspace.id
        is_cross = destination_makerspace_id != makerspace.id
        source = _container(data.get("source_container_id"), makerspace.id)
        # For a cross-makerspace move the destination container lives in the
        # destination makerspace; intra-makerspace keeps it in the same one.
        destination = _container(
            data.get("destination_container_id"),
            destination_makerspace_id if is_cross else makerspace.id,
        )
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
            if is_cross:
                _apply_cross_makerspace_line(
                    actor, transfer, makerspace, destination_makerspace_id, destination, line_data
                )
            else:
                _apply_intra_makerspace_line(
                    actor, transfer, makerspace, source, destination, line_data
                )
        audit.record(actor, "stock_transfer.applied", makerspace=makerspace, target=transfer)
        if is_cross:
            destination_makerspace = Makerspace.objects.get(pk=destination_makerspace_id)
            audit.record(
                actor,
                "stock_transfer.received",
                makerspace=destination_makerspace,
                target=transfer,
                meta={"source_makerspace_id": makerspace.id},
            )
        return transfer


def _apply_intra_makerspace_line(actor, transfer, makerspace, source, destination, line_data):
    """Relocate a product/asset between containers within one makerspace."""
    product = None
    asset = None
    split_created = False
    quantity = line_data.get("quantity") or 1
    if line_data.get("asset_id"):
        asset = InventoryAsset.objects.select_for_update().select_related("product").get(
            pk=line_data["asset_id"],
            makerspace=makerspace,
        )
        if source and asset.box_id != source.id:
            raise ValidationError({"asset_id": "Asset is not in the source container."})
        from_status = line_data.get("from_status") or ""
        if from_status and asset.status != from_status:
            raise ValidationError({"from_status": "Asset is not currently in this status."})
        to_status = line_data.get("to_status") or ""
        if to_status and to_status != asset.status:
            try:
                availability.move_asset_status(asset, to_status)
            except availability.InsufficientStock as exc:
                raise ValidationError({"to_status": str(exc)}) from exc
        asset.box = destination
        asset.save(update_fields=["box", "updated_at"])
        product = asset.product
    else:
        product = InventoryProduct.objects.select_for_update().get(
            pk=line_data["product_id"],
            makerspace=makerspace,
        )
        if source and product.box_id != source.id:
            raise ValidationError({"product_id": "Product is not in the source container."})
        destination_product, split_created = move_quantity_stock(
            product,
            destination,
            quantity,
        )
    StockTransferLine.objects.create(
        transfer=transfer,
        product=None if asset else product,
        asset=asset,
        quantity=quantity,
        from_status=line_data.get("from_status", ""),
        to_status=line_data.get("to_status", ""),
        notes=line_data.get("notes", ""),
    )
    adjustment_product = product
    if not asset and split_created:
        adjustment_product = destination_product
    InventoryAdjustment.objects.create(
        makerspace=makerspace,
        transfer=transfer,
        product=None if asset else adjustment_product,
        asset=asset,
        reason=transfer.reason,
        created_by=actor,
    )


def _apply_cross_makerspace_line(
    actor, transfer, source_makerspace, dest_makerspace_id, dest_container, line_data
):
    """Actually move available quantity stock from one makerspace to another.

    Quantity is decremented on the source product and credited to a find-or-create
    product (matched by name) in the destination makerspace. Individual-tracked
    products / explicit asset lines are rejected: relocating serialized units also
    means re-scoping their asset rows + QR codes across tenants, which is out of
    scope here — move quantity stock instead."""
    if line_data.get("asset_id"):
        raise ValidationError(
            {"asset_id": "Individual asset units cannot be moved across makerspaces; transfer quantity stock instead."}
        )
    quantity = line_data.get("quantity") or 1
    src = InventoryProduct.objects.select_for_update().get(
        pk=line_data["product_id"],
        makerspace=source_makerspace,
    )
    if src.tracking_mode == TrackingMode.INDIVIDUAL:
        raise ValidationError(
            {"product_id": "Individual-tracked products cannot be moved across makerspaces yet."}
        )
    if quantity > src.available_quantity:
        raise ValidationError({"quantity": "Cannot transfer more than the available stock."})

    dest_queryset = InventoryProduct.objects.select_for_update().filter(
        makerspace_id=dest_makerspace_id,
        name__iexact=src.name,
        category_id=src.category_id,
        box=dest_container,
        is_archived=False,
    )
    dest = dest_queryset.first()
    if dest is not None and dest.tracking_mode == TrackingMode.INDIVIDUAL:
        # Crediting quantity onto an individual-tracked product would create phantom
        # units with no backing InventoryAsset/QR rows. Refuse instead of corrupting.
        raise ValidationError(
            {"product_id": "Destination already has an individual-tracked product with this name."}
        )
    if dest is None:
        dest = InventoryProduct.objects.create(
            makerspace_id=dest_makerspace_id,
            name=src.name,
            description=src.description,
            tracking_mode=TrackingMode.QUANTITY,
            box=dest_container,
            total_quantity=0,
            available_quantity=0,
            # Don't auto-publish into the destination's public catalog; the
            # receiving makerspace opts in explicitly.
            is_public=False,
        )
    availability.transfer_available_quantity(src, dest, quantity)

    StockTransferLine.objects.create(
        transfer=transfer,
        product=src,
        asset=None,
        quantity=quantity,
        from_status=line_data.get("from_status", ""),
        to_status=line_data.get("to_status", ""),
        notes=line_data.get("notes", "") or f"Moved to makerspace #{dest_makerspace_id} product #{dest.id}",
    )
    InventoryAdjustment.objects.create(
        makerspace=source_makerspace,
        transfer=transfer,
        product=src,
        delta_available=-quantity,
        reason=transfer.reason,
        created_by=actor,
    )
    InventoryAdjustment.objects.create(
        makerspace_id=dest_makerspace_id,
        transfer=transfer,
        product=dest,
        delta_available=quantity,
        reason=transfer.reason,
        created_by=actor,
    )
