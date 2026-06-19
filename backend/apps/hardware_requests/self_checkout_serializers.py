from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


class PublicToolScanSerializer(serializers.Serializer):
    identifier = serializers.CharField()
    payload = serializers.CharField()


class PublicToolLoanItemSerializer(serializers.Serializer):
    product_name = serializers.CharField()
    quantity = serializers.IntegerField()


class PublicToolLoanSerializer(serializers.Serializer):
    public_token = serializers.UUIDField(source="request.public_token", read_only=True)
    status = serializers.CharField(read_only=True)
    target_type = serializers.CharField(read_only=True)
    target_label = serializers.CharField(read_only=True)
    items = serializers.SerializerMethodField()

    @extend_schema_field(PublicToolLoanItemSerializer(many=True))
    def get_items(self, obj) -> list[dict[str, object]]:
        if "items" in getattr(obj.request, "_prefetched_objects_cache", {}):
            items = sorted(obj.request.items.all(), key=lambda item: item.product.name)
        else:
            items = obj.request.items.select_related("product").order_by("product__name")
        return [
            {"product_name": item.product.name, "quantity": item.issued_quantity}
            for item in items
        ]
