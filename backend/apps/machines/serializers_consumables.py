from decimal import Decimal

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.inventory.models import InventoryProduct
from apps.machines.models import MachineConsumable


class MachineConsumableSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    available = serializers.SerializerMethodField()
    remaining = serializers.SerializerMethodField()

    class Meta:
        model = MachineConsumable
        fields = [
            "id",
            "measurement",
            "product",
            "product_name",
            "available",
            "remaining",
            "label",
            "low_threshold",
            "note",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_product_name(self, obj):
        return obj.product.name if obj.product_id else None

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_available(self, obj):
        return obj.product.available_quantity if obj.product_id else None

    @extend_schema_field(
        serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    )
    def get_remaining(self, obj):
        return obj.remaining if not obj.product_id else None


class LinkMachineConsumableSerializer(serializers.Serializer):
    measurement = serializers.ChoiceField(choices=MachineConsumable.Measurement.choices)
    product_id = serializers.PrimaryKeyRelatedField(
        source="product",
        queryset=InventoryProduct.objects.all(),
        required=False,
        allow_null=True,
    )
    label = serializers.CharField(max_length=200, required=False, allow_blank=True)
    remaining = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    low_threshold = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        allow_null=True,
    )
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)


class LogMachineConsumptionSerializer(serializers.Serializer):
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )


class ConsumableCandidateSerializer(serializers.ModelSerializer):
    available = serializers.IntegerField(source="available_quantity", read_only=True)

    class Meta:
        model = InventoryProduct
        fields = ["id", "name", "available"]
        read_only_fields = fields
