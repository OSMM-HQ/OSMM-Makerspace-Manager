from rest_framework import serializers


class MobilePaymentIntentResponseSerializer(serializers.Serializer):
    payment_id = serializers.IntegerField()
    client_secret = serializers.CharField()
    publishable_key = serializers.CharField()
    customer_id = serializers.CharField(required=False, allow_null=True)
    ephemeral_key = serializers.CharField(required=False, allow_null=True)
