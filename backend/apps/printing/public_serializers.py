from rest_framework import serializers


class PublicPrintBucketSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField()


class PrintCheckinVerifyRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField(trim_whitespace=True)


class PrintCheckinVerifyResponseSerializer(serializers.Serializer):
    username = serializers.CharField()
    external_id = serializers.CharField()


class PrintPresignRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField()
    kind = serializers.ChoiceField(choices=["stl", "screenshot"])
    filename = serializers.CharField(max_length=255)
    content_type = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=128,
    )


class PrintPresignResponseSerializer(serializers.Serializer):
    file_id = serializers.IntegerField()
    upload = serializers.DictField()


class PrintRequestSubmitSerializer(serializers.Serializer):
    website = serializers.CharField(required=False, allow_blank=True)
    identifier = serializers.CharField()
    bucket_id = serializers.IntegerField()
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True)
    project_brief = serializers.CharField(required=False, allow_blank=True)
    preferred_settings = serializers.CharField(required=False, allow_blank=True)
    material = serializers.CharField(required=False, allow_blank=True, max_length=100)
    color = serializers.CharField(required=False, allow_blank=True, max_length=100)
    quantity = serializers.IntegerField(min_value=1, default=1)
    source_link = serializers.CharField(required=False, allow_blank=True)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    contact_phone = serializers.CharField(required=False, allow_blank=True)
    file_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        default=list,
    )


class PrintRequestSubmitResponseSerializer(serializers.Serializer):
    public_token = serializers.UUIDField()
    status = serializers.CharField()


class PublicPrintStatusSerializer(serializers.Serializer):
    public_token = serializers.UUIDField()
    status = serializers.CharField()
    title = serializers.CharField()
    created_at = serializers.DateTimeField()
    accepted_at = serializers.DateTimeField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)
