from rest_framework import serializers


class TypedReportBaseSerializer(serializers.Serializer):
    makerspace_id = serializers.IntegerField(required=False)


class ReportRowsFieldMixin(serializers.Serializer):
    rows = serializers.ListField(
        child=serializers.ListField(child=serializers.JSONField())
    )
