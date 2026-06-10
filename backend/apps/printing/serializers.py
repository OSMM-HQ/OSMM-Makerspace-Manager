from rest_framework import serializers

from apps.printing.models import PrintBucket, PrintRequest


class ErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


class PrintBucketSerializer(serializers.ModelSerializer):
    makerspace = serializers.IntegerField(source="makerspace_id", read_only=True)

    class Meta:
        model = PrintBucket
        fields = (
            "id",
            "makerspace",
            "name",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class PrintRequestCreateSerializer(serializers.ModelSerializer):
    bucket = serializers.PrimaryKeyRelatedField(
        queryset=PrintBucket.objects.select_related("makerspace").all()
    )

    class Meta:
        model = PrintRequest
        fields = (
            "bucket",
            "title",
            "description",
            "material",
            "color",
            "quantity",
            "source_link",
        )

    def validate_bucket(self, value):
        if not value.is_active:
            raise serializers.ValidationError("Bucket is not active.")
        return value

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("Quantity must be at least 1.")
        return value

    def create(self, validated_data):
        return PrintRequest.objects.create(
            requester=self.context["request"].user,
            **validated_data,
        )


class PrintRequestSerializer(serializers.ModelSerializer):
    bucket = PrintBucketSerializer(read_only=True)
    makerspace = serializers.IntegerField(source="bucket.makerspace_id", read_only=True)
    requester = serializers.IntegerField(source="requester_id", read_only=True)
    requester_email = serializers.EmailField(source="requester.email", read_only=True)
    requester_username = serializers.CharField(
        source="requester.username", read_only=True
    )
    handled_by = serializers.IntegerField(source="handled_by_id", read_only=True)

    class Meta:
        model = PrintRequest
        fields = (
            "id",
            "bucket",
            "makerspace",
            "requester",
            "requester_email",
            "requester_username",
            "title",
            "description",
            "material",
            "color",
            "quantity",
            "source_link",
            "status",
            "reason",
            "handled_by",
            "created_at",
            "accepted_at",
            "completed_at",
            "updated_at",
        )
        read_only_fields = fields


class RejectFailSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)
