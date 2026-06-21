from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.accounts import rbac
from apps.accounts.models import User
from apps.audit import services as audit
from apps.boxes.asset_rebind import move_asset_across_makerspaces
from apps.boxes.models import QrCode, QrScanEvent
from apps.boxes.serializers import QrCodeSerializer, qr_target_payload
from apps.hardware_requests.self_checkout_workflow import qr_has_active_loan
from apps.inventory.models import InventoryAsset, InventoryProduct
from apps.makerspaces.guards import require_module


def rebind_qr_target(user, qr_id, data):
    qr = get_object_or_404(QrCode.objects.select_for_update(), pk=qr_id)
    if qr.status != QrCode.Status.ACTIVE:
        raise ValidationError("QR code is not active.")
    require_module(qr.makerspace, "qr_management")
    asset_move = data.get("destination_makerspace_id") and qr.target_type == QrCode.TargetType.ASSET
    if asset_move:
        return move_asset_across_makerspaces(
            user,
            qr,
            data["destination_makerspace_id"],
            data.get("destination_product_id"),
            data.get("new_name", ""),
            request_target_id=data.get("target_id"),
        )
    if qr_has_active_loan(qr.makerspace, qr):
        return Response(
            {"detail": "Cannot rebind a QR with an outstanding loan."},
            status=status.HTTP_409_CONFLICT,
        )

    target_type = data["target_type"]
    target = _locked_target(target_type, data["target_id"])
    cross = target.makerspace_id != qr.makerspace_id
    _require_rebind_permission(user, qr, target, target_type, cross, asset_move=False)
    if _target_has_qr(qr, target, target_type):
        return Response(
            {"detail": "Target already has an active QR code."},
            status=status.HTTP_409_CONFLICT,
        )

    old_meta = {
        "old_makerspace_id": qr.makerspace_id,
        "old_target_type": qr.target_type,
        "old_target_id": qr.target_id,
    }
    old_name = _target_name(target, target_type)
    qr.makerspace_id = target.makerspace_id
    qr.target_type = target_type
    qr.target_id = target.id
    try:
        with transaction.atomic():
            qr.save(update_fields=["makerspace", "target_type", "target_id", "updated_at"])
    except IntegrityError:
        return Response(
            {"detail": "Target already has an active QR code."},
            status=status.HTTP_409_CONFLICT,
        )

    new_name = data.get("new_name", "").strip()
    if new_name:
        _rename_target(user, target, target_type, old_name, new_name)
    QrScanEvent.objects.create(
        makerspace=qr.makerspace,
        qr_code=qr,
        actor=user,
        context=QrScanEvent.Context.REASSIGNMENT,
    )
    audit.record(
        user,
        "qr.rebound",
        makerspace=qr.makerspace,
        target=qr,
        meta={
            **old_meta,
            "new_makerspace_id": qr.makerspace_id,
            "new_target_type": target_type,
            "new_target_id": target.id,
            "new_name": new_name,
        },
    )
    return Response({"qr": QrCodeSerializer(qr).data, "target": qr_target_payload(qr)})


def _locked_target(target_type, target_id):
    if target_type == QrCode.TargetType.PRODUCT:
        return get_object_or_404(InventoryProduct.objects.select_for_update(), pk=target_id)
    return get_object_or_404(InventoryAsset.objects.select_for_update(), pk=target_id)


def _require_rebind_permission(user, qr, target, target_type, cross, asset_move=False):
    if user.access_status != User.AccessStatus.ACTIVE:
        raise PermissionDenied()
    if cross:
        if not (
            rbac.can(user, rbac.Action.TRANSFER_STOCK, qr.makerspace_id)
            and rbac.can(user, rbac.Action.TRANSFER_STOCK, target.makerspace_id)
        ):
            raise PermissionDenied()
        if not asset_move and (
            qr.target_type != QrCode.TargetType.PRODUCT
            or target_type != QrCode.TargetType.PRODUCT
        ):
            raise ValidationError("Only products can be rebound across makerspaces.")
        require_module(target.makerspace, "qr_management")
        return
    allowed = rbac.can(user, rbac.Action.MANAGE_QR, qr.makerspace_id) and rbac.can(
        user,
        rbac.Action.EDIT_INVENTORY,
        qr.makerspace_id,
    )
    if not allowed:
        raise PermissionDenied()


def _target_has_qr(qr, target, target_type):
    return (
        QrCode.objects.select_for_update()
        .filter(
            makerspace_id=target.makerspace_id,
            target_type=target_type,
            target_id=target.id,
            status=QrCode.Status.ACTIVE,
        )
        .exclude(pk=qr.pk)
        .exists()
    )


def _target_name(target, target_type):
    if target_type == QrCode.TargetType.ASSET:
        return target.asset_tag
    return target.name


def _rename_target(user, target, target_type, old_name, new_name):
    if target_type == QrCode.TargetType.PRODUCT:
        target.name = new_name
        target.save(update_fields=["name", "updated_at"])
    else:
        target.asset_tag = new_name
        try:
            with transaction.atomic():
                target.save(update_fields=["asset_tag", "updated_at"])
        except IntegrityError as exc:
            raise ValidationError("An asset with that tag already exists.") from exc
    audit.record(
        user,
        "inventory.renamed",
        makerspace=target.makerspace,
        target=target,
        meta={"old_name": old_name, "new_name": new_name},
    )
