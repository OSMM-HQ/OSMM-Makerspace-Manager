from rest_framework import serializers

from apps.makerspaces.models import Makerspace
from apps.printing.models import FilamentSpool, PrintBucket, PrintPrinter, PrintRequest


class ErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


class PrintBucketSerializer(serializers.ModelSerializer):
    makerspace = serializers.IntegerField(source="makerspace_id", read_only=True)

    class Meta:
        model = PrintBucket
        fields = (
            "id",
            "makerspace",
            "name",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class FilamentSpoolSummarySerializer(serializers.ModelSerializer):
    printer = serializers.IntegerField(source="printer_id", read_only=True)

    class Meta:
        model = FilamentSpool
        fields = (
            "id",
            "printer",
            "material",
            "color",
            "brand",
            "lot_code",
            "initial_weight_grams",
            "remaining_weight_grams",
            "is_active",
            "opened_at",
        )
        read_only_fields = fields


class PrintPrinterSerializer(serializers.ModelSerializer):
    makerspace = serializers.IntegerField(source="makerspace_id")
    active_spool = serializers.SerializerMethodField()
    current_request = serializers.SerializerMethodField()
    is_free = serializers.SerializerMethodField()
    pending_estimated_minutes = serializers.SerializerMethodField()
    estimated_spool_remaining_after_queue_grams = serializers.SerializerMethodField()

    class Meta:
        model = PrintPrinter
        fields = (
            "id",
            "makerspace",
            "name",
            "model",
            "status",
            "notes",
            "is_active",
            "active_spool",
            "current_request",
            "is_free",
            "pending_estimated_minutes",
            "estimated_spool_remaining_after_queue_grams",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "active_spool",
            "current_request",
            "is_free",
            "pending_estimated_minutes",
            "estimated_spool_remaining_after_queue_grams",
            "created_at",
            "updated_at",
        )

    def validate_makerspace(self, value):
        return value

    def validate(self, attrs):
        makerspace_id = attrs.get("makerspace_id") or getattr(
            self.instance, "makerspace_id", None
        )
        if not makerspace_id:
            raise serializers.ValidationError({"makerspace": "This field is required."})
        if not Makerspace.objects.filter(pk=makerspace_id).exists():
            raise serializers.ValidationError({"makerspace": "Unknown makerspace."})
        return attrs

    def get_active_spool(self, obj) -> dict | None:
        spool = (
            obj.filament_spools.filter(is_active=True)
            .order_by("-opened_at", "-created_at")
            .first()
        )
        if not spool:
            return None
        return FilamentSpoolSummarySerializer(spool).data

    def _queue(self, obj):
        return obj.print_requests.filter(
            status__in=[PrintRequest.Status.ACCEPTED, PrintRequest.Status.PRINTING]
        )

    def get_current_request(self, obj) -> dict | None:
        current = self._queue(obj).filter(status=PrintRequest.Status.PRINTING).first()
        if not current:
            return None
        return {
            "id": current.id,
            "title": current.title,
            "estimated_minutes": current.estimated_minutes,
        }

    def get_is_free(self, obj) -> bool:
        if not obj.is_active or obj.status != PrintPrinter.Status.ACTIVE:
            return False
        return not self._queue(obj).filter(status=PrintRequest.Status.PRINTING).exists()

    def get_pending_estimated_minutes(self, obj) -> int:
        return sum(request.estimated_minutes for request in self._queue(obj))

    def get_estimated_spool_remaining_after_queue_grams(self, obj) -> str | None:
        spool = (
            obj.filament_spools.filter(is_active=True)
            .order_by("-opened_at", "-created_at")
            .first()
        )
        if not spool:
            return None
        pending_grams = sum(
            request.estimated_filament_grams
            for request in self._queue(obj).filter(filament_spool=spool)
        )
        estimated = max(spool.remaining_weight_grams - pending_grams, 0)
        return f"{estimated:.2f}"


class FilamentSpoolSerializer(serializers.ModelSerializer):
    makerspace = serializers.IntegerField(source="makerspace_id")
    printer_name = serializers.CharField(source="printer.name", read_only=True)

    class Meta:
        model = FilamentSpool
        fields = (
            "id",
            "makerspace",
            "printer",
            "printer_name",
            "material",
            "color",
            "brand",
            "lot_code",
            "initial_weight_grams",
            "remaining_weight_grams",
            "is_active",
            "opened_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "printer_name", "created_at", "updated_at")

    def validate(self, attrs):
        makerspace_id = attrs.get("makerspace_id") or getattr(
            self.instance, "makerspace_id", None
        )
        printer = attrs.get("printer") or getattr(self.instance, "printer", None)
        if not makerspace_id:
            raise serializers.ValidationError({"makerspace": "This field is required."})
        if printer and printer.makerspace_id != makerspace_id:
            raise serializers.ValidationError(
                {"printer": "Printer must belong to the same makerspace."}
            )
        remaining = attrs.get("remaining_weight_grams")
        initial = attrs.get("initial_weight_grams")
        if initial is not None and remaining is not None and remaining > initial:
            raise serializers.ValidationError(
                {"remaining_weight_grams": "Remaining weight cannot exceed initial weight."}
            )
        return attrs


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
    makerspace = serializers.IntegerField(source="bucket.makerspace_id", read_only=True)
    requester = serializers.IntegerField(source="requester_id", read_only=True)
    requester_email = serializers.EmailField(source="requester.email", read_only=True)
    requester_username = serializers.CharField(
        source="requester.username", read_only=True
    )
    handled_by = serializers.IntegerField(source="handled_by_id", read_only=True)

    class Meta:
        model = PrintRequest
        fields = (
            "id",
            "bucket",
            "makerspace",
            "requester",
            "requester_email",
            "requester_username",
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
            "status",
            "reason",
            "handled_by",
            "printer",
            "filament_spool",
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
