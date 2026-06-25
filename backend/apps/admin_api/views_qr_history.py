from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff
from apps.boxes.models import QrCode, QrScanEvent
from apps.inventory.models import InventoryAsset, InventoryProduct
from apps.makerspaces.guards import require_module


class QrHistoryItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    source = serializers.CharField()
    context = serializers.CharField()
    actor = serializers.IntegerField(allow_null=True)
    created_at = serializers.DateTimeField()


class ProductQrHistorySerializer(serializers.Serializer):
    product = serializers.IntegerField()
    scans = QrHistoryItemSerializer(many=True)


class AssetQrHistorySerializer(serializers.Serializer):
    asset = serializers.IntegerField()
    scans = QrHistoryItemSerializer(many=True)


class ProductQrHistoryView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Admin inventory"],
        summary="List QR scan history for an inventory product",
        responses={200: ProductQrHistorySerializer},
    )
    def get(self, request, pk, *args, **kwargs):
        product = get_object_or_404(
            rbac.scope_by_action(
                request.user,
                rbac.Action.VIEW_INVENTORY,
                InventoryProduct.objects.select_related("makerspace"),
            ),
            pk=pk,
        )
        require_module(product.makerspace_id, "staff_admin")
        return Response(
            {
                "product": product.id,
                "scans": _history_rows(
                    product.makerspace_id,
                    QrCode.TargetType.PRODUCT,
                    product.id,
                ),
            }
        )


class AssetQrHistoryView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Admin inventory"],
        summary="List QR scan history for an inventory asset",
        responses={200: AssetQrHistorySerializer},
    )
    def get(self, request, pk, *args, **kwargs):
        asset = get_object_or_404(
            rbac.scope_by_action(
                request.user,
                rbac.Action.VIEW_INVENTORY,
                InventoryAsset.objects.select_related("makerspace", "product"),
            ),
            pk=pk,
        )
        require_module(asset.makerspace_id, "staff_admin")
        return Response(
            {
                "asset": asset.id,
                "scans": _history_rows(
                    asset.makerspace_id,
                    QrCode.TargetType.ASSET,
                    asset.id,
                ),
            }
        )


def _history_rows(makerspace_id, target_type, target_id):
    events = (
        QrScanEvent.objects.select_related("actor")
        .filter(
            makerspace_id=makerspace_id,
            qr_code__target_type=target_type,
            qr_code__target_id=target_id,
        )
        .order_by("-created_at")
    )
    return [
        {
            "id": f"qr-{event.id}",
            "source": "qr_scan",
            "context": event.context,
            "actor": event.actor_id,
            "created_at": event.created_at,
        }
        for event in events
    ]