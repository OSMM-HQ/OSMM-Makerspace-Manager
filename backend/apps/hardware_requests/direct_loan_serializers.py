from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.hardware_requests.self_checkout_serializers import PublicToolLoanSerializer


class DirectLoanItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class DirectLoanIssueSerializer(serializers.Serializer):
    identifier = serializers.CharField()
    container_id = serializers.IntegerField(required=False, allow_null=True)
    qr_payloads = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )
    items = DirectLoanItemSerializer(many=True, required=False, allow_empty=True)

    def validate(self, attrs):
        if (
            not attrs.get("qr_payloads")
            and not attrs.get("items")
            and attrs.get("container_id") is None
        ):
            raise serializers.ValidationError(
                "Provide qr_payloads, items, or a container."
            )
        return attrs


class DirectLoanReturnSerializer(serializers.Serializer):
    evidence_id = serializers.IntegerField()
    notes = serializers.CharField()
    returned_by_identifier = serializers.CharField(required=False, allow_blank=True)


class DirectLoanUserAttributionSerializer(serializers.Serializer):
    username = serializers.CharField()
    role = serializers.CharField()


class DirectLoanSerializer(PublicToolLoanSerializer):
    id = serializers.IntegerField(read_only=True)
    container_id = serializers.IntegerField(read_only=True)
    container_label = serializers.SerializerMethodField()
    due_at = serializers.DateTimeField(read_only=True, allow_null=True)
    return_evidence_id = serializers.IntegerField(read_only=True, allow_null=True)
    return_notes = serializers.CharField(read_only=True, allow_blank=True)
    source = serializers.CharField(read_only=True)
    issued_by = serializers.SerializerMethodField()

    def get_container_label(self, obj):
        return obj.container.label if obj.container else None

    @extend_schema_field(DirectLoanUserAttributionSerializer(allow_null=True))
    def get_issued_by(self, obj):
        user = getattr(obj.request, "issued_by", None)
        if user is None:
            return None
        return {"username": user.username, "role": user.role}


class StaffCheckinVerifyRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField()


class StaffCheckinVerifyResponseSerializer(serializers.Serializer):
    username = serializers.CharField(read_only=True)
