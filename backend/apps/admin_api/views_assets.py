from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff, require_action
from apps.admin_api.serializers_inventory import (
    InventoryAssetAdminSerializer,
    InventoryAssetStatusActionSerializer,
)
from apps.admin_api.views_inventory import InventoryPagination
from apps.audit import services as audit
from apps.inventory import availability
from apps.inventory.models import InventoryAsset, InventoryProduct, TrackingMode
from apps.makerspaces.guards import require_module


class InventoryAssetListView(generics.ListAPIView):
    serializer_class = InventoryAssetAdminSerializer
    permission_classes = [IsActiveStaff]
    pagination_class = InventoryPagination

    @extend_schema(
        tags=["Admin inventory"],
        summary="List individual assets for an inventory product",
        responses=InventoryAssetAdminSerializer(many=True),
    )
    def get(self, request, product_pk, *args, **kwargs):
        return super().get(request, product_pk, *args, **kwargs)

    def get_queryset(self):
        product = get_object_or_404(
            rbac.scope_by_action(
                self.request.user,
                rbac.Action.VIEW_INVENTORY,
                InventoryProduct.objects.all(),
            ),
            pk=self.kwargs["product_pk"],
        )
        require_module(product.makerspace_id, "staff_admin")
        return (
            InventoryAsset.objects.select_related("product", "box", "makerspace")
            .filter(product=product)
            .order_by("asset_tag", "id")
        )


class InventoryAssetStatusActionView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Admin inventory"],
        summary="Move a specific individual asset to or from the fix shelf",
        request=InventoryAssetStatusActionSerializer,
        responses={200: InventoryAssetAdminSerializer},
    )
    def post(self, request, pk, *args, **kwargs):
        asset = get_object_or_404(
            rbac.scope_by_action(
                request.user,
                rbac.Action.VIEW_INVENTORY,
                InventoryAsset.objects.select_related("product", "makerspace", "box"),
            ),
            pk=pk,
        )
        require_module(asset.makerspace_id, "staff_admin")
        require_action(request.user, rbac.Action.EDIT_INVENTORY, asset.makerspace_id)
        if asset.product.tracking_mode != TrackingMode.INDIVIDUAL:
            raise ValidationError("Asset fix actions are only for individual-tracked products.")

        serializer = InventoryAssetStatusActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]
        target_status = (
            InventoryAsset.Status.MAINTENANCE
            if action == "shelve"
            else InventoryAsset.Status.AVAILABLE
        )
        if action == "shelve" and asset.status not in {
            InventoryAsset.Status.AVAILABLE,
            InventoryAsset.Status.DAMAGED,
        }:
            raise ValidationError("Only available or damaged assets can be moved to the fix shelf.")
        if action == "repair" and asset.status != InventoryAsset.Status.MAINTENANCE:
            raise ValidationError("Only assets on the fix shelf can be moved back to inventory.")

        try:
            with transaction.atomic():
                locked_asset = InventoryAsset.objects.select_for_update().select_related("product", "makerspace").get(pk=asset.pk)
                availability.move_asset_status(locked_asset, target_status)
                audit.record(
                    request.user,
                    f"inventory.asset_needs_fix_{action}",
                    makerspace=locked_asset.makerspace,
                    target=locked_asset,
                    meta={"product_id": locked_asset.product_id, "asset_tag": locked_asset.asset_tag},
                )
        except availability.InsufficientStock as exc:
            raise ValidationError(str(exc)) from exc
        locked_asset.refresh_from_db()
        return Response(InventoryAssetAdminSerializer(locked_asset).data)