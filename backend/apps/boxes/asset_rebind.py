from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts import rbac
from apps.accounts.models import User
from apps.audit import services as audit
from apps.boxes.exceptions import Conflict
from apps.boxes.models import QrCode, QrScanEvent
from apps.boxes.rebind_results import QrRebindResult
from apps.hardware_requests.models import HardwareRequest, PublicToolLoan
from apps.hardware_requests.asset_link_models import HardwareRequestItemAsset
from apps.hardware_requests.self_checkout_workflow import qr_has_active_loan
from apps.inventory import availability
from apps.inventory.availability import InsufficientStock
from apps.inventory.models import InventoryAsset, InventoryProduct, TrackingMode
from apps.makerspaces.guards import require_module


OUTSTANDING_REQUEST_STATUSES = (
    HardwareRequest.Status.ISSUED,
    HardwareRequest.Status.PARTIALLY_RETURNED,
)


def move_asset_across_makerspaces(
    user, qr, dest_makerspace_id, destination_product_id, new_name, request_target_id=None
):
    if qr.target_type != QrCode.TargetType.ASSET:
        raise ValidationError("QR code does not target an asset.")
    if request_target_id is not None and int(request_target_id) != qr.target_id:
        raise ValidationError("target_id must match the scanned asset.")

    asset = InventoryAsset.objects.select_for_update().get(pk=qr.target_id)
    source_makerspace_id = qr.makerspace_id
    _require_transfer_permission(user, source_makerspace_id, dest_makerspace_id)
    if int(dest_makerspace_id) == source_makerspace_id:
        raise ValidationError("Destination makerspace must be different.")

    dest_makerspace = require_module(dest_makerspace_id, "qr_management")
    _guard_asset_is_movable(asset, qr)

    source_product_id = asset.product_id
    candidate_ids = _destination_candidate_ids(
        asset.product.name,
        dest_makerspace.id,
        destination_product_id,
    )
    locked_products = {
        product.id: product
        for product in InventoryProduct.objects.select_for_update()
        .filter(pk__in={source_product_id, *candidate_ids})
        .order_by("pk")
    }
    source_product = locked_products[source_product_id]
    dest_product = _resolve_destination_product(
        locked_products,
        dest_makerspace,
        source_product,
        candidate_ids,
        destination_product_id,
    )
    old_tag = asset.asset_tag
    final_tag = (new_name or "").strip() or old_tag
    if (
        InventoryAsset.objects.filter(makerspace_id=dest_makerspace.id, asset_tag=final_tag)
        .exclude(pk=asset.pk)
        .exists()
    ):
        raise Conflict("An asset with that tag already exists in the destination makerspace.")

    asset.product = dest_product
    asset.makerspace = dest_makerspace
    asset.box = None
    asset.public_self_checkout_enabled = False
    asset.asset_tag = final_tag
    try:
        with transaction.atomic():
            asset.save(update_fields=[
                "product", "makerspace", "box", "public_self_checkout_enabled",
                "asset_tag", "updated_at",
            ])
    except IntegrityError as exc:
        raise Conflict("An asset with that tag already exists in the destination makerspace.") from exc

    qr.makerspace = dest_makerspace
    try:
        with transaction.atomic():
            qr.save(update_fields=["makerspace", "updated_at"])
    except IntegrityError as exc:
        raise Conflict("Target already has an active QR code.") from exc

    try:
        availability.adjust_quantities(
            source_product,
            delta_available=-1,
            delta_damaged=0,
            delta_lost=0,
            reason="Cross-makerspace asset move (out)",
            actor=user,
        )
        availability.adjust_quantities(
            dest_product,
            delta_available=1,
            delta_damaged=0,
            delta_lost=0,
            reason="Cross-makerspace asset move (in)",
            actor=user,
        )
    except InsufficientStock as exc:
        raise Conflict(str(exc)) from exc

    QrScanEvent.objects.create(
        makerspace=dest_makerspace,
        qr_code=qr,
        actor=user,
        context=QrScanEvent.Context.REASSIGNMENT,
    )
    audit.record(
        user,
        "inventory.asset_moved_makerspace",
        makerspace=dest_makerspace,
        target=asset,
        meta={
            "old_makerspace_id": source_makerspace_id,
            "new_makerspace_id": dest_makerspace.id,
            "asset_id": asset.id,
            "dest_product_id": dest_product.id,
            "old_tag": old_tag,
            "new_tag": final_tag,
        },
    )
    return QrRebindResult(qr=qr)


def _require_transfer_permission(user, source_makerspace_id, dest_makerspace_id):
    if user.access_status != User.AccessStatus.ACTIVE:
        raise PermissionDenied()
    if not (
        rbac.can(user, rbac.Action.TRANSFER_STOCK, source_makerspace_id)
        and rbac.can(user, rbac.Action.TRANSFER_STOCK, dest_makerspace_id)
    ):
        raise PermissionDenied()


def _guard_asset_is_movable(asset, qr):
    if asset.status != InventoryAsset.Status.AVAILABLE:
        raise Conflict("asset is not available to move")
    if qr_has_active_loan(qr.makerspace, qr):
        raise Conflict("Cannot move an asset with an outstanding loan.")
    if HardwareRequestItemAsset.objects.filter(
        asset=asset,
        outcome=HardwareRequestItemAsset.Outcome.ISSUED,
        request_item__request__status__in=OUTSTANDING_REQUEST_STATUSES,
    ).exists():
        raise Conflict("Cannot move an asset linked to an outstanding request.")
    if PublicToolLoan.objects.filter(
        makerspace=qr.makerspace,
        status=PublicToolLoan.Status.CHECKED_OUT,
        asset_ids__contains=[asset.id],
    ).exists():
        raise Conflict("Cannot move an asset with an outstanding loan.")


def _destination_candidate_ids(product_name, dest_makerspace_id, destination_product_id):
    if destination_product_id is not None:
        return {int(destination_product_id)}
    return set(
        InventoryProduct.objects.filter(
            makerspace_id=dest_makerspace_id,
            is_archived=False,
            name__iexact=product_name,
        ).values_list("id", flat=True)
    )


def _resolve_destination_product(
    locked_products, dest_makerspace, source_product, candidate_ids, destination_product_id
):
    if destination_product_id is not None:
        product = locked_products.get(int(destination_product_id))
        if (
            product is None
            or product.makerspace_id != dest_makerspace.id
            or product.tracking_mode != TrackingMode.INDIVIDUAL
            or product.is_archived
        ):
            raise ValidationError("destination_product_id must be an unarchived individual product in the destination makerspace.")
        return product

    candidates = [locked_products[pk] for pk in sorted(candidate_ids) if pk in locked_products]
    if any(product.tracking_mode == TrackingMode.QUANTITY for product in candidates):
        raise Conflict("destination has a quantity-tracked product with this name")
    individual = next(
        (product for product in candidates if product.tracking_mode == TrackingMode.INDIVIDUAL),
        None,
    )
    if individual is not None:
        return individual
    return InventoryProduct.objects.create(
        makerspace=dest_makerspace,
        name=source_product.name,
        tracking_mode=TrackingMode.INDIVIDUAL,
        is_public=False,
        total_quantity=0,
        available_quantity=0,
        box=None,
    )
