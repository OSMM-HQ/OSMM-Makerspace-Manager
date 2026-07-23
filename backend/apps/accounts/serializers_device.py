from rest_framework import serializers

from apps.accounts.models_devices import DeviceEnvironment, DevicePlatform


class DeviceIdentitySerializer(serializers.Serializer):
    platform = serializers.ChoiceField(choices=DevicePlatform.choices)
    app_id = serializers.RegexField(r"^[A-Za-z0-9._-]{3,255}$", max_length=255)
    environment = serializers.ChoiceField(choices=DeviceEnvironment.choices)


class DeviceLoginSerializer(DeviceIdentitySerializer):
    username = serializers.CharField(max_length=254, trim_whitespace=True)
    password = serializers.CharField(max_length=1024, write_only=True, trim_whitespace=False)
    challenge = serializers.CharField(max_length=512, trim_whitespace=False)
    attestation = serializers.JSONField()

    def validate_attestation(self, value):
        if not isinstance(value, dict) or not value or len(value) > 16:
            raise serializers.ValidationError("Invalid attestation payload.")
        return value


class DeviceRefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField(max_length=4096, write_only=True, trim_whitespace=False)


class DeviceGrantSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    platform = serializers.CharField()
    app_id = serializers.CharField()
    environment = serializers.CharField()
    status = serializers.CharField()
    attested_at = serializers.DateTimeField()
    last_used_at = serializers.DateTimeField()
    created_at = serializers.DateTimeField()


class DeviceTokenResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = serializers.DictField()
    device_grant = DeviceGrantSerializer()


class DeviceChallengeResponseSerializer(serializers.Serializer):
    challenge = serializers.CharField()
    expires_in = serializers.IntegerField(min_value=1)


class DeviceRefreshResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    device_grant = DeviceGrantSerializer()


class DeviceLogoutResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
