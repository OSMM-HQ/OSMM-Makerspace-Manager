from rest_framework import serializers

from apps.admin_api import bulk_import
from apps.admin_api.models import BulkImportJob


class BulkImportPreviewSerializer(serializers.Serializer):
    file = serializers.FileField(required=False)
    rows = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=False,
        max_length=bulk_import.MAX_IMPORT_ROWS,
    )
    mapping = serializers.DictField(child=serializers.CharField(), required=False)

    def validate(self, attrs):
        return _validate_import_payload(attrs)


class BulkImportJobCreateSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=BulkImportJob.Mode.choices)
    file = serializers.FileField(required=False)
    rows = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=False,
        max_length=bulk_import.MAX_IMPORT_ROWS,
    )
    mapping = serializers.DictField(child=serializers.CharField(), required=False)

    def validate(self, attrs):
        return _validate_import_payload(attrs)


class BulkImportJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = BulkImportJob
        fields = [
            "id",
            "mode",
            "status",
            "total_rows",
            "processed_rows",
            "created_count",
            "updated_count",
            "error_count",
            "warning_count",
            "result",
            "error",
            "created_at",
            "updated_at",
            "completed_at",
        ]
        read_only_fields = fields


def _validate_import_payload(attrs):
    has_file = bool(attrs.get("file"))
    has_rows = bool(attrs.get("rows"))
    if not has_file and not has_rows:
        raise serializers.ValidationError("Provide either file or rows.")
    if has_file and has_rows:
        raise serializers.ValidationError("Provide file or rows, not both.")
    uploaded_file = attrs.get("file")
    if uploaded_file and uploaded_file.size > bulk_import.MAX_IMPORT_UPLOAD_BYTES:
        raise serializers.ValidationError(
            {
                "file": (
                    "Import file must be "
                    f"{bulk_import.MAX_IMPORT_UPLOAD_BYTES} bytes or smaller."
                )
            }
        )
    return attrs
