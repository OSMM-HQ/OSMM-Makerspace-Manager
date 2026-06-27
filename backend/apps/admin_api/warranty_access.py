from django.shortcuts import get_object_or_404

from apps.accounts import rbac
from apps.admin_api.permissions import require_action
from apps.inventory.models import InventoryAsset
from apps.makerspaces.guards import require_module
from apps.printing.models import PrintPrinter
from apps.warranty.models import Warranty, WarrantyDocument


def resolve_asset_host(user, asset_pk):
    return get_object_or_404(
        rbac.scope_by_makerspace(
            user,
            InventoryAsset.objects.select_related("makerspace"),
        ),
        pk=asset_pk,
    )


def resolve_printer_host(user, printer_pk):
    return get_object_or_404(
        rbac.scope_by_makerspace(
            user,
            PrintPrinter.objects.select_related("makerspace"),
        ),
        pk=printer_pk,
    )


def resolve_warranty(user, warranty_pk):
    return get_object_or_404(
        rbac.scope_by_makerspace(
            user,
            Warranty.objects.select_related("makerspace", "asset", "printer"),
            "makerspace_id",
        ),
        pk=warranty_pk,
    )


def resolve_document(user, doc_pk):
    return get_object_or_404(
        rbac.scope_by_makerspace(
            user,
            WarrantyDocument.objects.select_related(
                "warranty",
                "warranty__asset",
                "warranty__printer",
            ),
            "warranty__makerspace_id",
        ),
        pk=doc_pk,
    )


def action_and_module_for_warranty(warranty):
    if warranty.asset_id:
        return rbac.Action.EDIT_INVENTORY, "staff_admin"
    return rbac.Action.MANAGE_PRINTING, "printing"


def enforce(user, warranty):
    action, module = action_and_module_for_warranty(warranty)
    require_action(user, action, warranty.makerspace_id)
    require_module(warranty.makerspace_id, module)
