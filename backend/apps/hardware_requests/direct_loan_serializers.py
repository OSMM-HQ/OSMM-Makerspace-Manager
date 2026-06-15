from rest_framework import serializers

from apps.hardware_requests.self_checkout_serializers import PublicToolLoanSerializer


class DirectLoanItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class DirectLoanIssueSerializer(serializers.Serializer):
    identifier = serializers.CharField()
    qr_payloads = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )
    items = DirectLoanItemSerializer(many=True, required=False, allow_empty=True)

    def validate(self, attrs):
        if not attrs.get("qr_payloads") and not attrs.get("items"):
            raise serializers.ValidationError("Provide qr_payloads or items.")
        return attrs


class DirectLoanReturnSerializer(serializers.Serializer):
    returned_by_identifier = serializers.CharField(required=False, allow_blank=True)


class DirectLoanSerializer(PublicToolLoanSerializer):
    id = serializers.IntegerField(read_only=True)
    due_at = serializers.DateTimeField(read_only=True, allow_null=True)
    source = serializers.CharField(read_only=True)
