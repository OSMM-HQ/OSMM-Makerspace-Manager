from decimal import Decimal

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.printing.models import ManualPrintLog


class ManualPrintLogSerializer(serializers.ModelSerializer):
    makerspace_id = serializers.IntegerField()
    printer_id = serializers.IntegerField(allow_null=True)
    filament_spool_id = serializers.IntegerField(allow_null=True)
    grams_used = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        max_value=Decimal("999999.99"),
    )
    duration_minutes = serializers.IntegerField(
        min_value=0,
        max_value=100000,
        required=False,
        default=0,
    )
    outcome = serializers.ChoiceField(
        choices=ManualPrintLog.Outcome.choices,
        required=False,
        default=ManualPrintLog.Outcome.SUCCESS,
    )
    percent_complete = serializers.IntegerField(
        min_value=0,
        max_value=100,
        required=False,
        default=100,
    )
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    printer_name = serializers.CharField(
        source="printer.name",
        read_only=True,
        allow_null=True,
    )
    spool_label = serializers.SerializerMethodField()
    requester_name = serializers.CharField(required=False, allow_blank=True, max_length=120)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    contact_phone = serializers.CharField(required=False, allow_blank=True, max_length=40)
    logged_by_username = serializers.CharField(
        source="logged_by.username",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = ManualPrintLog
        fields = (
            "id",
            "makerspace_id",
            "printer_id",
            "filament_spool_id",
            "grams_used",
            "duration_minutes",
            "outcome",
            "percent_complete",
            "reason",
            "title",
            "requester_name",
            "contact_email",
            "contact_phone",
            "note",
            "created_at",
            "printer_name",
            "spool_label",
            "logged_by_username",
        )
        read_only_fields = (
            "id",
            "created_at",
            "printer_name",
            "spool_label",
            "logged_by_username",
        )

    def validate_grams_used(self, value):
        if value <= 0:
            raise serializers.ValidationError("Must be greater than 0.")
        return value

    def validate(self, attrs):
        if attrs.get("outcome") == ManualPrintLog.Outcome.FAILED and not (
            attrs.get("reason") or ""
        ).strip():
            raise serializers.ValidationError(
                {"reason": "A failure reason is required for a failed print."}
            )
        return attrs

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_spool_label(self, obj):
        spool = obj.filament_spool
        if not spool:
            return None
        parts = [spool.brand, spool.material, spool.color]
        return " ".join(part for part in parts if part).strip() or spool.material
