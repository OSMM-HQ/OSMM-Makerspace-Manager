from rest_framework import serializers

from apps.boxes.models import Box, QrCode, QrScanEvent
from apps.inventory.models import InventoryAsset, InventoryProduct


class BoxSerializer(serializers.ModelSerializer):
    class Meta:
        model = Box
        fields = [
            "id",
            "makerspace",
            "parent",
            "code",
            "label",
            "location",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "code", "created_at", "updated_at"]


class QrCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = QrCode
        fields = [
            "id",
            "makerspace",
            "payload",
            "target_type",
            "target_id",
            "status",
            "created_at",
            "updated_at",
            "revoked_at",
        ]
        read_only_fields = ["id", "payload", "status", "created_at", "updated_at", "revoked_at"]


class CreateBoxQrSerializer(serializers.Serializer):
    makerspace_id = serializers.IntegerField()
    label = serializers.CharField()
    location = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    parent_id = serializers.IntegerField(required=False, allow_null=True)


class CreateToolQrSerializer(serializers.Serializer):
    makerspace_id = serializers.IntegerField()
    product_id = serializers.IntegerField(required=False)
    asset_id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if bool(attrs.get("product_id")) == bool(attrs.get("asset_id")):
            raise serializers.ValidationError("Provide exactly one of product_id or asset_id.")
        return attrs


class QrScanSerializer(serializers.Serializer):
    payload = serializers.CharField()
    context = serializers.ChoiceField(choices=QrScanEvent.Context.choices)
    request_id = serializers.IntegerField(required=False, allow_null=True)


class QrScanResultSerializer(serializers.Serializer):
    qr = QrCodeSerializer()
    target = serializers.DictField()
    scan_id = serializers.IntegerField()


class QrResolveSerializer(serializers.Serializer):
    payload = serializers.CharField()


class QrResolveResultSerializer(serializers.Serializer):
    qr = QrCodeSerializer()
    target = serializers.DictField()
    allowed_actions = serializers.ListField(child=serializers.CharField())


def qr_target_payload(qr):
    if qr.target_type == QrCode.TargetType.BOX:
        box = Box.objects.get(pk=qr.target_id)
        return {"type": "box", "id": box.id, "label": box.label, "code": box.code}
    if qr.target_type == QrCode.TargetType.ASSET:
        asset = InventoryAsset.objects.select_related("product").get(pk=qr.target_id)
        return {
            "type": "asset",
            "id": asset.id,
            "asset_tag": asset.asset_tag,
            "product": asset.product.name,
            "status": asset.status,
        }
    product = InventoryProduct.objects.get(pk=qr.target_id)
    return {"type": "product", "id": product.id, "name": product.name}
