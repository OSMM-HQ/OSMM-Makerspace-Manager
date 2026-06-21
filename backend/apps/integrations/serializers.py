from rest_framework import serializers


class TelegramWebhookSerializer(serializers.Serializer):
    update_id = serializers.IntegerField(required=False)
    callback_query = serializers.DictField(required=False)


class TelegramTestAlertSerializer(serializers.Serializer):
    makerspace_id = serializers.IntegerField()
    message = serializers.CharField(default="OSMM test alert.")
