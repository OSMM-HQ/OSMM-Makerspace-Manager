from rest_framework import serializers

from apps.inventory import public_image_storage
from apps.makerspaces.models import Makerspace
from apps.printing.models import PrintPrinter, PrintRequest
from apps.printing.serializers_spools import FilamentSpoolSummarySerializer


class PrintPrinterSerializer(serializers.ModelSerializer):
    makerspace = serializers.IntegerField(source="makerspace_id")
    active_spool = serializers.SerializerMethodField()
    current_request = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
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
            "image_url",
            "is_active",
            "active_spool",
            "current_request",
            "image_url",
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

    def create(self, validated_data):
        makerspace_id = validated_data.pop("makerspace_id")
        return PrintPrinter.objects.create(
            makerspace_id=makerspace_id,
            **validated_data,
        )

    def update(self, instance, validated_data):
        if "makerspace_id" in validated_data:
            makerspace_id = validated_data.pop("makerspace_id")
            if makerspace_id != instance.makerspace_id:
                instance.image_key = ""
            instance.makerspace_id = makerspace_id
        return super().update(instance, validated_data)

    def get_image_url(self, obj) -> str | None:
        return public_image_storage.public_url(obj.image_key) or None

    def _active_spool_obj(self, obj):
        if hasattr(obj, "_active_spools"):
            return obj._active_spools[0] if obj._active_spools else None
        return (
            obj.filament_spools.filter(is_active=True)
            .order_by("-opened_at", "-created_at")
            .first()
        )

    def _queue_list(self, obj):
        if hasattr(obj, "_queue_requests"):
            return obj._queue_requests
        return list(
            obj.print_requests.filter(
                status__in=[PrintRequest.Status.ACCEPTED, PrintRequest.Status.PRINTING]
            )
        )

    def get_active_spool(self, obj) -> dict | None:
        spool = self._active_spool_obj(obj)
        if not spool:
            return None
        return FilamentSpoolSummarySerializer(spool).data

    def get_current_request(self, obj) -> dict | None:
        current = None
        for request in self._queue_list(obj):
            if request.status == PrintRequest.Status.PRINTING:
                current = request
                break
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
        return not any(
            request.status == PrintRequest.Status.PRINTING
            for request in self._queue_list(obj)
        )

    def get_pending_estimated_minutes(self, obj) -> int:
        return sum(request.estimated_minutes for request in self._queue_list(obj))

    def get_estimated_spool_remaining_after_queue_grams(self, obj) -> str | None:
        spool = self._active_spool_obj(obj)
        if not spool:
            return None
        pending_grams = sum(
            request.estimated_filament_grams
            for request in self._queue_list(obj)
            if request.filament_spool_id == spool.id
            and request.status == PrintRequest.Status.ACCEPTED
        )
        estimated = max(spool.remaining_weight_grams - pending_grams, 0)
        return f"{estimated:.2f}"
