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
    remaining_weight_grams = serializers.DecimalField(max_digits=8, decimal_places=2)


class PrintCheckinVerifyRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField(trim_whitespace=True)


class PrintCheckinVerifyResponseSerializer(serializers.Serializer):
    # Only a display name — never the stable Check-In external_id (avoids identifier
    # disclosure; the server re-verifies the identifier on submit anyway).
    username = serializers.CharField()


class PrintPresignRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField()
    kind = serializers.ChoiceField(choices=["stl", "screenshot"])
    filename = serializers.CharField(max_length=255)
    content_type = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=128,
    )


class PrintPresignResponseSerializer(serializers.Serializer):
    file_id = serializers.IntegerField()
    upload = serializers.DictField()


class PrintRequestSubmitSerializer(serializers.Serializer):
    website = serializers.CharField(required=False, allow_blank=True)
    identifier = serializers.CharField()
    bucket_id = serializers.IntegerField(required=False, allow_null=True)
    requester_name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=120,
    )
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True)
    project_brief = serializers.CharField(required=False, allow_blank=True)
    preferred_settings = serializers.CharField(required=False, allow_blank=True)
    material = serializers.CharField(required=False, allow_blank=True, max_length=100)
    color = serializers.CharField(required=False, allow_blank=True, max_length=100)
    filament_spool_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1, default=1)
    # Bound to the model column limits so overlong input is a clean 400, not a DB DataError.
    source_link = serializers.URLField(required=False, allow_blank=True, max_length=200)
    contact_email = serializers.EmailField(required=False, allow_blank=True, max_length=254)
    contact_phone = serializers.CharField(required=False, allow_blank=True, max_length=40)
    file_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        default=list,
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
    # Lets the public page show a live "time left" while printing
    # (estimated finish = started_at + estimated_minutes).
    estimated_minutes = serializers.IntegerField()
    # Populated only while the request is pending/accepted; null otherwise.
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
