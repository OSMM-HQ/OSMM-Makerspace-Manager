from rest_framework import serializers


class MembershipRequestCreateSerializer(serializers.Serializer):
    website = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate_website(self, value):
        if value:
            raise serializers.ValidationError("Invalid request.")
        return value


class WaiverPublishSerializer(serializers.Serializer):
    body = serializers.CharField(required=False, allow_blank=True)
    version = serializers.CharField(required=False, allow_blank=True, max_length=64)
    clear = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if not attrs.get("clear") and (not attrs.get("body") or not attrs.get("version")):
            raise serializers.ValidationError("Body and version are required unless clearing the waiver.")
        return attrs
