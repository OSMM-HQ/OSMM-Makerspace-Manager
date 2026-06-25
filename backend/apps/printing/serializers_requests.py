from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.hardware_requests.display import label_from_candidates
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
        if value.makerspace.archived_at is not None:
            raise serializers.ValidationError("Makerspace is archived.")
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


class PrintRequestFileSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    kind = serializers.CharField()
    content_type = serializers.CharField()
    size_bytes = serializers.IntegerField()


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
    reprint_of = serializers.IntegerField(source="reprint_of_id", read_only=True)
    files = serializers.SerializerMethodField()

    @extend_schema_field(PrintRequestFileSummarySerializer(many=True))
    def get_files(self, obj):
        files = list(obj.files.all())
        if not files and obj.reprint_of_id:
            files = list(obj.reprint_of.files.all())
        return [
            {
                "id": f.id,
                "kind": f.kind,
                "content_type": f.content_type,
                "size_bytes": f.size_bytes,
            }
            for f in files
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
            "filament_grams_used",
            "filament_grams_reserved",
            "reprint_of",
            "created_at",
            "accepted_at",
            "started_at",
            "completed_at",
            "updated_at",
        )
        read_only_fields = fields



class PrintRequestActorSerializer(serializers.Serializer):
    username = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)


class ManagedPrintRequestSerializer(PrintRequestSerializer):
    accepted_by = PrintRequestActorSerializer(read_only=True, allow_null=True)
    collected_by = serializers.IntegerField(source="collected_by_id", read_only=True)
    # Staff-only readable label, never the internal checkin_<hash> username.
    requester_display = serializers.SerializerMethodField()

    def get_requester_display(self, obj) -> str:
        return label_from_candidates(
            obj.requester_name,
            obj.contact_email,
            obj.contact_phone,
            getattr(obj.requester, "external_checkin_user_id", ""),
            getattr(obj.requester, "username", ""),
        )

    class Meta(PrintRequestSerializer.Meta):
        fields = PrintRequestSerializer.Meta.fields + (
            "requester_display",
            "price",
            "payment_status",
            "paid_at",
            "accepted_by",
            "collected_at",
            "collected_by",
        )
        read_only_fields = fields


class PrintAcceptSerializer(serializers.Serializer):
    price = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        min_value=0,
        required=False,
        default=0,
    )


class RejectFailSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)


class CompletePrintSerializer(serializers.Serializer):
    actual_filament_grams = serializers.DecimalField(
        required=False,
        allow_null=True,
        max_digits=8,
        decimal_places=2,
        min_value=0,
    )


class FailPrintSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)
    percent_complete = serializers.IntegerField(
        min_value=0,
        max_value=100,
        required=True,
    )


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
