from rest_framework import serializers

from apps.integrations.models_push import PushDevice


class PushDeviceRegistrationSerializer(serializers.Serializer):
    token = serializers.RegexField(
        r"^[A-Za-z0-9_:.-]{20,4096}$", max_length=4096,
        write_only=True, trim_whitespace=False,
    )
    provider = serializers.ChoiceField(choices=PushDevice.Provider.choices)
    environment = serializers.ChoiceField(choices=PushDevice.Environment.choices)


class PushDeviceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    provider = serializers.CharField()
    environment = serializers.CharField()
    makerspace_id = serializers.IntegerField()
    active = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
