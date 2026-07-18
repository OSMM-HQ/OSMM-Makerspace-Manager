from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


class PublicPrintBucketSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField()


class PublicFilamentSpoolSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    material = serializers.CharField()
    color = serializers.CharField()


class PrintPresignRequestSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["stl", "screenshot"])
    filename = serializers.CharField(max_length=255)
    content_type = serializers.CharField(required=False, allow_blank=True, max_length=128)


class PrintPresignResponseSerializer(serializers.Serializer):
    file_id = serializers.IntegerField()
    upload = serializers.DictField()


class PrintRequestSubmitSerializer(serializers.Serializer):
    website = serializers.CharField(required=False, allow_blank=True)
    bucket_id = serializers.IntegerField(required=False, allow_null=True)
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True)
    project_brief = serializers.CharField(required=False, allow_blank=True)
    preferred_settings = serializers.CharField(required=False, allow_blank=True)
    material = serializers.CharField(required=False, allow_blank=True, max_length=100)
    color = serializers.CharField(required=False, allow_blank=True, max_length=100)
    filament_spool_id = serializers.IntegerField(required=False, allow_null=True)
    estimated_filament_grams = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=0, required=False, allow_null=True
    )
    quantity = serializers.IntegerField(min_value=1, default=1)
    source_link = serializers.URLField(required=False, allow_blank=True, max_length=200)
    file_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True, default=list
    )


class PrintRequestSubmitResponseSerializer(serializers.Serializer):
    public_token = serializers.UUIDField()
    status = serializers.CharField()


class PublicPrintStatusSerializer(serializers.Serializer):
    public_token = serializers.UUIDField()
    status = serializers.CharField()
    title = serializers.CharField()
    created_at = serializers.DateTimeField()
    accepted_at = serializers.DateTimeField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)
    estimated_minutes = serializers.IntegerField()
    queue_position = serializers.SerializerMethodField()
    queue_approved_ahead = serializers.SerializerMethodField()
    queue_awaiting_review_ahead = serializers.SerializerMethodField()

    @extend_schema_field({"type": "integer", "nullable": True})
    def get_queue_position(self, obj):
        counts = self.context.get("queue_counts", {}).get(obj.id)
        return counts["position"] if counts else None

    @extend_schema_field({"type": "integer", "nullable": True})
    def get_queue_approved_ahead(self, obj):
        counts = self.context.get("queue_counts", {}).get(obj.id)
        return counts["approved_ahead"] if counts else None

    @extend_schema_field({"type": "integer", "nullable": True})
    def get_queue_awaiting_review_ahead(self, obj):
        counts = self.context.get("queue_counts", {}).get(obj.id)
        return counts["awaiting_review_ahead"] if counts else None
