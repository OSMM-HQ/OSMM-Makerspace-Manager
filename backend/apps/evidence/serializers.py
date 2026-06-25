from django.conf import settings
from rest_framework import serializers

from apps.evidence.models import EvidencePhoto


class EvidenceUrlRequestSerializer(serializers.Serializer):
    evidence_type = serializers.ChoiceField(choices=EvidencePhoto.EvidenceType.choices)
    content_type = serializers.CharField()
    size_bytes = serializers.IntegerField(required=False, allow_null=True, min_value=0)

    def validate_content_type(self, value):
        if value not in settings.EVIDENCE_ALLOWED_MIME:
            raise serializers.ValidationError("Unsupported evidence content type.")
        return value


class EvidenceUrlResponseSerializer(serializers.Serializer):
    evidence_id = serializers.IntegerField()
    upload_url = serializers.URLField()
    fields = serializers.DictField()
    object_key = serializers.CharField()
    method = serializers.CharField(required=False)
    headers = serializers.DictField(required=False)


class EvidenceGetResponseSerializer(serializers.Serializer):
    url = serializers.URLField()
    expires_in = serializers.IntegerField()
