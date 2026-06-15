from rest_framework import serializers

from apps.printing.models import PrintBucket, PrintRequest
from apps.printing.serializers_buckets import PrintBucketSerializer
from apps.printing.serializers_printers import PrintPrinterSerializer
from apps.printing.serializers_spools import FilamentSpoolSummarySerializer


class PrintRequestCreateSerializer(serializers.ModelSerializer):
    bucket = serializers.PrimaryKeyRelatedField(
        queryset=PrintBucket.objects.select_related("makerspace").all()
    )

    class Meta:
        model = PrintRequest
        fields = (
            "bucket",
            "title",
            "description",
            "material",
            "color",
            "quantity",
            "source_link",
            "model_file",
            "preferred_settings",
            "estimate_screenshot",
            "preview_screenshot",
        )

    def validate_bucket(self, value):
        if not value.is_active:
            raise serializers.ValidationError("Bucket is not active.")
        return value

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("Quantity must be at least 1.")
        return value

    def create(self, validated_data):
        return PrintRequest.objects.create(
            requester=self.context["request"].user,
            **validated_data,
        )


class PrintRequestSerializer(serializers.ModelSerializer):
    bucket = PrintBucketSerializer(read_only=True)
    printer = PrintPrinterSerializer(read_only=True)
    filament_spool = FilamentSpoolSummarySerializer(read_only=True)
    # Requester's filament preference from public submit (distinct from the operational
    # filament_spool staff assign at start) — surfaced so staff can honor the exact spool.
    requested_filament_spool = FilamentSpoolSummarySerializer(read_only=True)
    makerspace = serializers.IntegerField(source="bucket.makerspace_id", read_only=True)
    requester = serializers.IntegerField(source="requester_id", read_only=True)
    requester_email = serializers.EmailField(source="requester.email", read_only=True)
    requester_username = serializers.CharField(
        source="requester.username", read_only=True
    )
    handled_by = serializers.IntegerField(source="handled_by_id", read_only=True)
    files = serializers.SerializerMethodField()

    def get_files(self, obj):
        return [
            {
                "id": f.id,
                "kind": f.kind,
                "content_type": f.content_type,
                "size_bytes": f.size_bytes,
            }
            for f in obj.files.all()
        ]

    class Meta:
        model = PrintRequest
        fields = (
            "id",
            "bucket",
            "makerspace",
            "requester",
            "requester_email",
            "requester_username",
            "requester_name",
            "title",
            "description",
            "material",
            "color",
            "quantity",
            "source_link",
            "model_file",
            "preferred_settings",
            "estimate_screenshot",
            "preview_screenshot",
            "project_brief",
            "contact_email",
            "contact_phone",
            "files",
            "status",
            "reason",
            "handled_by",
            "printer",
            "filament_spool",
            "requested_filament_spool",
            "estimated_minutes",
            "estimated_filament_grams",
            "created_at",
            "accepted_at",
            "started_at",
            "completed_at",
            "updated_at",
        )
        read_only_fields = fields


class RejectFailSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)


class PrintStartSerializer(serializers.Serializer):
    printer_id = serializers.IntegerField(required=False)
    filament_spool_id = serializers.IntegerField(required=False)
    estimated_minutes = serializers.IntegerField(required=False, min_value=0)
    estimated_filament_grams = serializers.DecimalField(
        required=False,
        max_digits=8,
        decimal_places=2,
        min_value=0,
    )
