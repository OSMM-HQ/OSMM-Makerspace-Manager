from decimal import Decimal

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
    printer_name = serializers.CharField(
        source="printer.name",
        read_only=True,
        allow_null=True,
    )
    spool_label = serializers.SerializerMethodField()
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
            "title",
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

    def get_spool_label(self, obj):
        spool = obj.filament_spool
        if not spool:
            return None
        parts = [spool.brand, spool.material, spool.color]
        return " ".join(part for part in parts if part).strip() or spool.material
