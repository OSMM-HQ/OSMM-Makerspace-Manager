from django.shortcuts import get_object_or_404

from apps.accounts import rbac
from apps.boxes.models import QrCode
from apps.inventory.models import InventoryAsset, InventoryProduct
from apps.makerspaces.models import Makerspace


def makerspace_for_action(user, action, makerspace_id):
    queryset = rbac.scope_by_action(user, action, Makerspace.objects.all(), field="id")
    return get_object_or_404(queryset, pk=makerspace_id)


def qr_for_action(user, action, **filters):
    queryset = rbac.scope_by_action(user, action, QrCode.objects.all())
    return get_object_or_404(queryset, **filters)


def locked_qr_for_action(user, action, **filters):
    queryset = rbac.scope_by_action(user, action, QrCode.objects.select_for_update())
    return get_object_or_404(queryset, **filters)


def target_for_rebind(user, target_type, target_id):
    action = rbac.Action.EDIT_INVENTORY
    if target_type == QrCode.TargetType.PRODUCT:
        queryset = rbac.scope_by_action(user, action, InventoryProduct.objects.select_for_update())
    else:
        queryset = rbac.scope_by_action(user, action, InventoryAsset.objects.select_for_update())
    return get_object_or_404(queryset, pk=target_id)
