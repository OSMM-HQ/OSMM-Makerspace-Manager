from rest_framework import serializers

from apps.accounts.models_social import (
    SocialClientPlatform,
    SocialDelivery,
    SocialProvider,
    SocialSurface,
)


class SocialNonceSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=SocialProvider.choices)
    surface = serializers.ChoiceField(choices=SocialSurface.choices)
    delivery = serializers.ChoiceField(choices=SocialDelivery.choices)
    client_platform = serializers.ChoiceField(choices=SocialClientPlatform.choices)

    def validate(self, attrs):
        if (attrs["delivery"] == "web") != (attrs["client_platform"] == "web"):
            raise serializers.ValidationError(
                "Web delivery requires the web client platform."
            )
        return attrs


class SocialLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField(max_length=16384, write_only=True)
    nonce = serializers.CharField(max_length=512, write_only=True)
    surface = serializers.ChoiceField(choices=SocialSurface.choices)
    delivery = serializers.ChoiceField(choices=SocialDelivery.choices)
    client_platform = serializers.ChoiceField(choices=SocialClientPlatform.choices)
    apple_name = serializers.CharField(
        max_length=200, required=False, allow_blank=True, trim_whitespace=True
    )

    def validate(self, attrs):
        if (attrs["delivery"] == "web") != (attrs["client_platform"] == "web"):
            raise serializers.ValidationError("Invalid social delivery platform.")
        return attrs


class SocialLinkSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=SocialProvider.choices)
    id_token = serializers.CharField(max_length=16384, write_only=True)
    nonce = serializers.CharField(max_length=512, write_only=True)
    client_platform = serializers.ChoiceField(
        choices=SocialClientPlatform.choices, default=SocialClientPlatform.WEB
    )
    apple_name = serializers.CharField(
        max_length=200, required=False, allow_blank=True, trim_whitespace=True
    )

    def validate_client_platform(self, value):
        if value != SocialClientPlatform.WEB:
            raise serializers.ValidationError("Browser linking requires the web client.")
        return value


class SocialIdentitySerializer(serializers.Serializer):
    provider = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class SocialNonceResponseSerializer(serializers.Serializer):
    nonce = serializers.CharField()
    expires_in = serializers.IntegerField()


class SocialLoginResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField(required=False)
    device_grant = serializers.DictField(required=False)
    user = serializers.DictField()
    outcome = serializers.CharField()
