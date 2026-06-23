from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit
from apps.inventory.models import InventoryAsset, InventoryProduct
from apps.operations.models import (
    InventoryAdjustment,
    StocktakeLedgerEntry,
    StocktakeLine,
    StocktakeSession,
)
from apps.operations.services_shared import _container


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
    with transaction.atomic():
        locked = StocktakeSession.objects.select_for_update().get(pk=stocktake.pk)
        if locked.status not in {StocktakeSession.Status.DRAFT, StocktakeSession.Status.COUNTING}:
            raise ValidationError("Cannot add count lines after stocktake is completed.")
        product = None
        asset = None
        expected = 0
        condition = data.get("condition") or StocktakeLine.Condition.AVAILABLE
        container = _container(data.get("container_id"), locked.makerspace_id)
        _validate_line_container(locked, container)
        if data.get("asset_id"):
            asset = InventoryAsset.objects.get(pk=data["asset_id"], makerspace=locked.makerspace)
            _validate_asset_count(asset, data["counted_quantity"])
            _validate_item_container(locked, container, asset=asset)
            expected = 1 if _asset_bucket(asset.status) == condition else 0
        else:
            product = InventoryProduct.objects.get(pk=data["product_id"], makerspace=locked.makerspace)
            _validate_item_container(locked, container, product=product)
            expected = _product_expected(product, condition)
        _reject_duplicate_line(locked, product, asset, condition, container)
        counted = data["counted_quantity"]
        try:
            line = StocktakeLine.objects.create(
                stocktake=locked,
                product=product,
                asset=asset,
                container=container,
                expected_quantity=expected,
                counted_quantity=counted,
                variance_quantity=counted - expected,
                condition=condition,
                notes=data.get("notes", ""),
            )
        except IntegrityError as exc:
            raise ValidationError("Duplicate stocktake line.") from exc
        audit.record(actor, "stocktake.line_counted", makerspace=locked.makerspace, target=locked, meta={"line_id": line.id})
        return line


def complete_stocktake(actor, stocktake):
    with transaction.atomic():
        locked = StocktakeSession.objects.select_for_update().get(pk=stocktake.pk)
        if locked.status != StocktakeSession.Status.COUNTING:
            raise ValidationError("Only counting stocktakes can be completed.")
        locked.status = StocktakeSession.Status.COMPLETED
        locked.completed_at = timezone.now()
        locked.save(update_fields=["status", "completed_at"])
        audit.record(actor, "stocktake.completed", makerspace=locked.makerspace, target=locked)
        return locked


def approve_stocktake(actor, stocktake):
    with transaction.atomic():
        locked = StocktakeSession.objects.select_for_update().get(pk=stocktake.pk)
        if locked.status != StocktakeSession.Status.COMPLETED:
            raise ValidationError("Only completed stocktakes can be approved.")
        locked.status = StocktakeSession.Status.APPROVED
        locked.approved_by = actor
        locked.approved_at = timezone.now()
        locked.save(update_fields=["status", "approved_by", "approved_at"])
        audit.record(actor, "stocktake.approved", makerspace=locked.makerspace, target=locked)
        return locked


def apply_stocktake_adjustments(actor, stocktake):
    with transaction.atomic():
        locked = StocktakeSession.objects.select_for_update().get(pk=stocktake.pk)
        if locked.status != StocktakeSession.Status.APPROVED:
            raise ValidationError("Only approved stocktakes can be applied.")
        for line in locked.lines.select_related("product", "asset", "container"):
            _validate_line_scope(locked, line)
            _validate_line_fresh(line)
            entries = _ledger_entries_for_line(actor, locked, line)
            _apply_ledger_entries(entries)
            _record_adjustment(actor, locked, line, entries)
        locked.status = StocktakeSession.Status.APPLIED
        locked.save(update_fields=["status"])
        audit.record(actor, "stocktake.adjustments_applied", makerspace=locked.makerspace, target=locked)
        return locked


def _product_expected(product, condition):
    if condition == StocktakeLine.Condition.AVAILABLE:
        return product.available_quantity
    if condition == StocktakeLine.Condition.DAMAGED:
        return product.damaged_quantity
    if condition == StocktakeLine.Condition.LOST:
        return product.lost_quantity
    return 0


def _asset_bucket(status):
    return {
        InventoryAsset.Status.AVAILABLE: StocktakeLedgerEntry.Bucket.AVAILABLE,
        InventoryAsset.Status.DAMAGED: StocktakeLedgerEntry.Bucket.DAMAGED,
        InventoryAsset.Status.LOST: StocktakeLedgerEntry.Bucket.LOST,
    }.get(status)


def _asset_new_status(line):
    if line.counted_quantity == 0:
        return InventoryAsset.Status.LOST
    if line.condition == StocktakeLine.Condition.DAMAGED:
        return InventoryAsset.Status.DAMAGED
    if line.condition == StocktakeLine.Condition.LOST:
        return InventoryAsset.Status.LOST
    return InventoryAsset.Status.AVAILABLE


def _validate_line_scope(stocktake, line):
    if line.product_id and line.product.makerspace_id != stocktake.makerspace_id:
        raise ValidationError("Stocktake line product belongs to another makerspace.")
    if line.asset_id:
        if line.asset.makerspace_id != stocktake.makerspace_id:
            raise ValidationError("Stocktake line asset belongs to another makerspace.")
        if line.asset.product_id != line.product_id and line.product_id is not None:
            raise ValidationError("Stocktake line asset and product do not match.")
        _validate_asset_count(line.asset, line.counted_quantity)
    if line.container_id and line.container.makerspace_id != stocktake.makerspace_id:
        raise ValidationError("Stocktake line container belongs to another makerspace.")
    _validate_line_container(stocktake, line.container)
    _validate_item_container(stocktake, line.container, product=line.product, asset=line.asset)


def _validate_line_container(stocktake, container):
    if not stocktake.container_id:
        return
    # Container-scoped stocktakes are exact: child boxes are out of scope unless
    # they are counted by their own stocktake scoped to that child box.
    if container is None or container.pk != stocktake.container_id:
        raise ValidationError({"container_id": "Count line must match the stocktake container."})


def _validate_item_container(stocktake, container, *, product=None, asset=None):
    scope = stocktake.container or container
    if scope is None:
        return
    if product is not None and product.box_id != scope.id:
        raise ValidationError({"product_id": "Product is outside the stocktake container."})
    if asset is not None and asset.box_id != scope.id:
        raise ValidationError({"asset_id": "Asset is outside the stocktake container."})


def _reject_duplicate_line(stocktake, product, asset, condition, container):
    lines = StocktakeLine.objects.filter(stocktake=stocktake)
    if asset is not None:
        if lines.filter(asset=asset).exists():
            raise ValidationError("Asset has already been counted in this stocktake.")
        return
    duplicates = lines.filter(product=product, condition=condition)
    duplicates = duplicates.filter(container=container) if container else duplicates.filter(container__isnull=True)
    if duplicates.exists():
        raise ValidationError("Product bucket has already been counted in this stocktake.")


def _validate_line_fresh(line):
    if line.condition == StocktakeLine.Condition.UNKNOWN:
        return
    if line.asset_id:
        asset = InventoryAsset.objects.select_for_update().get(pk=line.asset_id)
        current = 1 if _asset_bucket(asset.status) == line.condition else 0
    else:
        product = InventoryProduct.objects.select_for_update().get(pk=line.product_id)
        current = _product_expected(product, line.condition)
    if current != line.expected_quantity:
        raise ValidationError("Stocktake line is stale; recount before applying.")


def _validate_asset_count(asset, counted_quantity):
    if counted_quantity not in (0, 1):
        raise ValidationError({"counted_quantity": "Asset stocktake counts must be 0 or 1."})
    if _asset_bucket(asset.status) is None:
        raise ValidationError(
            {"asset_id": "Only available, damaged, or lost assets can be stocktaken."}
        )


def _ledger_entries_for_line(actor, stocktake, line):
    if line.condition == StocktakeLine.Condition.UNKNOWN:
        raise ValidationError("Unknown stocktake condition cannot be applied.")
    if line.asset_id:
        return _asset_ledger_entries(actor, stocktake, line)
    if line.variance_quantity == 0:
        return []
    return [
        _create_ledger_entry(
            actor,
            stocktake,
            line,
            bucket=line.condition,
            delta=line.variance_quantity,
        )
    ]


def _asset_ledger_entries(actor, stocktake, line):
    asset = InventoryAsset.objects.select_for_update().get(pk=line.asset_id)
    old_status = asset.status
    new_status = _asset_new_status(line)
    entries = []
    old_bucket = _asset_bucket(old_status)
    new_bucket = _asset_bucket(new_status)
    if old_bucket == new_bucket:
        asset.status = new_status
        asset.save(update_fields=["status", "updated_at"])
        return entries
    if old_bucket:
        entries.append(_create_ledger_entry(actor, stocktake, line, bucket=old_bucket, delta=-1, old_status=old_status, new_status=new_status))
    if new_bucket:
        entries.append(_create_ledger_entry(actor, stocktake, line, bucket=new_bucket, delta=1, old_status=old_status, new_status=new_status))
    asset.status = new_status
    asset.save(update_fields=["status", "updated_at"])
    return entries


def _create_ledger_entry(actor, stocktake, line, *, bucket, delta, old_status="", new_status=""):
    return StocktakeLedgerEntry.objects.create(
        makerspace=stocktake.makerspace,
        stocktake=stocktake,
        line=line,
        product=line.product or (line.asset.product if line.asset_id else None),
        asset=line.asset,
        bucket=bucket,
        delta=delta,
        old_asset_status=old_status,
        new_asset_status=new_status,
        reason=f"Stocktake #{stocktake.id}: {line.notes}".strip(),
        created_by=actor,
    )


def _apply_ledger_entries(entries):
    for entry in entries:
        product = InventoryProduct.objects.select_for_update().get(pk=entry.product_id)
        if entry.bucket == StocktakeLedgerEntry.Bucket.AVAILABLE:
            product.available_quantity += entry.delta
        elif entry.bucket == StocktakeLedgerEntry.Bucket.DAMAGED:
            product.damaged_quantity += entry.delta
        elif entry.bucket == StocktakeLedgerEntry.Bucket.LOST:
            product.lost_quantity += entry.delta
        if min(product.available_quantity, product.damaged_quantity, product.lost_quantity) < 0:
            raise ValidationError("Stocktake adjustment would make inventory negative.")
        _save_product_totals(product)


def _save_product_totals(product):
    product.total_quantity = (
        product.available_quantity
        + product.reserved_quantity
        + product.issued_quantity
        + product.damaged_quantity
        + product.lost_quantity
        + product.needs_fix_quantity
    )
    product.save()


def _record_adjustment(actor, stocktake, line, entries):
    if not entries:
        return
    deltas = {entry.bucket: entry.delta for entry in entries}
    InventoryAdjustment.objects.create(
        makerspace=stocktake.makerspace,
        stocktake=stocktake,
        product=line.product or (line.asset.product if line.asset_id else None),
        asset=line.asset,
        delta_available=deltas.get(StocktakeLedgerEntry.Bucket.AVAILABLE, 0),
        delta_damaged=deltas.get(StocktakeLedgerEntry.Bucket.DAMAGED, 0),
        delta_lost=deltas.get(StocktakeLedgerEntry.Bucket.LOST, 0),
        reason=f"Stocktake #{stocktake.id}: {line.notes}".strip(),
        created_by=actor,
    )
