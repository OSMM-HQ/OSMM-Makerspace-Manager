from rest_framework import serializers

from apps.procurement.models import ToBuyItem, ToBuyReceipt


class ToBuyReceiptSerializer(serializers.ModelSerializer):
    uploaded_by_username = serializers.CharField(
        source="uploaded_by.username",
        read_only=True,
        default=None,
    )

    class Meta:
        model = ToBuyReceipt
        fields = [
            "id",
            "created_at",
            "uploaded_by",
            "uploaded_by_username",
        ]
        read_only_fields = fields


class ToBuyItemSerializer(serializers.ModelSerializer):
    # kind is decided server-side from the actor's role (see access.derive_kind),
    # never written from the request body - so it is read-only here.
    created_by_username = serializers.CharField(
        source="created_by.username",
        read_only=True,
        default=None,
    )
    purchaser = serializers.PrimaryKeyRelatedField(read_only=True)
    purchaser_username = serializers.CharField(
        source="purchaser.username",
        read_only=True,
        default=None,
    )
    receipts = ToBuyReceiptSerializer(many=True, read_only=True)
    # Declared explicitly with min_value=1 so the OpenAPI schema advertises
    # minimum: 1 - matching the server rule that quantity must be >= 1.
    quantity = serializers.IntegerField(min_value=1, default=1)

    class Meta:
        model = ToBuyItem
        fields = [
            "id",
            "makerspace",
            "kind",
            "name",
            "quantity",
            "link",
            "status",
            "estimated_unit_cost",
            "vendor_name",
            "actual_unit_cost",
            "purchaser",
            "purchaser_username",
            "ordered_at",
            "received_at",
            "receipts",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "makerspace",
            "kind",
            "purchaser",
            "purchaser_username",
            "ordered_at",
            "received_at",
            "receipts",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        ]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name is required.")
        return value

    def validate_vendor_name(self, value):
        return value.strip()

    def validate_estimated_unit_cost(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Estimated unit cost cannot be negative.")
        return value

    def validate_actual_unit_cost(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Actual unit cost cannot be negative.")
        return value


class ToBuyReceiptPresignSerializer(serializers.Serializer):
    filename = serializers.CharField(allow_blank=False, max_length=255)
    content_type = serializers.CharField(allow_blank=False, max_length=100)


class ToBuyReceiptFinalizeSerializer(serializers.Serializer):
    object_key = serializers.CharField(allow_blank=False, max_length=512)


class ToBuyReceiptUploadResponseSerializer(serializers.Serializer):
    object_key = serializers.CharField()
    upload = serializers.DictField()


class ToBuyReceiptUrlSerializer(serializers.Serializer):
    url = serializers.URLField()
