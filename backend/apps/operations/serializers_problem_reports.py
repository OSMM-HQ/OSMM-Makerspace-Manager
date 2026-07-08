from rest_framework import serializers


class ProblemReportTriageResolutionSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class ProblemReportTriageSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(
        choices=["no_issue", "damaged", "missing", "needs_fix"]
    )
    resolutions = ProblemReportTriageResolutionSerializer(
        many=True, required=False, default=list
    )
    note = serializers.CharField(required=False, allow_blank=True, default="")
    evidence_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs):
        resolutions = attrs.get("resolutions", [])
        item_ids = [entry["item_id"] for entry in resolutions]
        if len(item_ids) != len(set(item_ids)):
            raise serializers.ValidationError(
                {"resolutions": "Duplicate item_id values are not allowed."}
            )
        if attrs["outcome"] != "no_issue" and not resolutions:
            raise serializers.ValidationError(
                {"resolutions": "At least one item must be triaged."}
            )
        return attrs


class ProblemReportTriageResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    outcome = serializers.CharField()
    resolved = serializers.BooleanField()