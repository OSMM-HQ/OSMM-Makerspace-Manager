from rest_framework import serializers

from apps.integrations.models import NotificationChannel, NotificationFeature


class NotificationRuleCatalogItemSerializer(serializers.Serializer):
    stream = serializers.CharField()
    audience = serializers.CharField()
    targets = serializers.ListField(child=serializers.CharField())
    events = serializers.ListField(child=serializers.CharField())


class NotificationRuleMuteSerializer(serializers.Serializer):
    target = serializers.CharField()
    stream = serializers.CharField()
    event = serializers.CharField()
    audience = serializers.CharField()


class NotificationChannelSerializer(serializers.Serializer):
    key = serializers.ChoiceField(choices=NotificationChannel.choices)
    label = serializers.CharField()


class NotificationFeatureSerializer(serializers.Serializer):
    key = serializers.ChoiceField(choices=NotificationFeature.choices)
    label = serializers.CharField()
    events = serializers.ListField(child=serializers.CharField())


class NotificationPreferenceCellSerializer(serializers.Serializer):
    feature = serializers.ChoiceField(choices=NotificationFeature.choices)
    channel = serializers.ChoiceField(choices=NotificationChannel.choices)
    enabled = serializers.BooleanField()
    source = serializers.ChoiceField(choices=("default", "override"))


class NotificationRulesResponseSerializer(serializers.Serializer):
    catalog = NotificationRuleCatalogItemSerializer(many=True)
    mutes = NotificationRuleMuteSerializer(many=True)
    channels = NotificationChannelSerializer(many=True)
    features = NotificationFeatureSerializer(many=True)
    preferences = NotificationPreferenceCellSerializer(many=True)


class NotificationRuleChangeSerializer(serializers.Serializer):
    target = serializers.CharField()
    stream = serializers.CharField()
    event = serializers.CharField()
    audience = serializers.CharField()
    muted = serializers.BooleanField()


class StrictBooleanField(serializers.BooleanField):
    def to_internal_value(self, data):
        if type(data) is not bool:
            raise serializers.ValidationError("Must be a valid boolean.")
        return data


class NotificationPreferenceChangeSerializer(serializers.Serializer):
    feature = serializers.ChoiceField(choices=NotificationFeature.choices)
    channel = serializers.ChoiceField(choices=NotificationChannel.choices)
    enabled = StrictBooleanField()


class NotificationRulesPatchSerializer(serializers.Serializer):
    changes = NotificationRuleChangeSerializer(many=True, required=False)
    preferences = NotificationPreferenceChangeSerializer(many=True, required=False)

    def validate(self, attrs):
        if not attrs.get("changes") and not attrs.get("preferences"):
            raise serializers.ValidationError(
                "At least one non-empty changes or preferences list is required."
            )
        return attrs
