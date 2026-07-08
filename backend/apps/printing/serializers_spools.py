from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.makerspaces.models import Makerspace
from apps.printing.models import FilamentAdjustment, FilamentSpool


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


class FilamentSpoolSerializer(serializers.ModelSerializer):
    makerspace = serializers.IntegerField(source="makerspace_id")
    printer_name = serializers.CharField(source="printer.name", read_only=True)
    ledger_adjustment_count = serializers.SerializerMethodField()
    ledger_balance_grams = serializers.SerializerMethodField()
    ledger_used_grams = serializers.SerializerMethodField()
    ledger_remaining_weight_grams = serializers.SerializerMethodField()

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
            "ledger_adjustment_count",
            "ledger_balance_grams",
            "ledger_used_grams",
            "ledger_remaining_weight_grams",
            "is_active",
            "opened_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "printer_name",
            "ledger_adjustment_count",
            "ledger_balance_grams",
            "ledger_used_grams",
            "ledger_remaining_weight_grams",
            "created_at",
            "updated_at",
        )

    @extend_schema_field(serializers.IntegerField)
    def get_ledger_adjustment_count(self, obj):
        return self._ledger_totals(obj)["count"]

    @extend_schema_field(serializers.DecimalField(max_digits=10, decimal_places=2))
    def get_ledger_balance_grams(self, obj):
        return str(self._ledger_totals(obj)["balance"])

    @extend_schema_field(serializers.DecimalField(max_digits=10, decimal_places=2))
    def get_ledger_used_grams(self, obj):
        totals = self._ledger_totals(obj)
        if totals["count"] == 0:
            return str(max(obj.initial_weight_grams - obj.remaining_weight_grams, Decimal("0.00")))
        return str(max(-totals["balance"], Decimal("0.00")))

    @extend_schema_field(serializers.DecimalField(max_digits=10, decimal_places=2))
    def get_ledger_remaining_weight_grams(self, obj):
        totals = self._ledger_totals(obj)
        if totals["count"] == 0:
            return str(obj.remaining_weight_grams)
        return str(obj.initial_weight_grams + totals["balance"])

    def _ledger_totals(self, obj):
        cached = getattr(obj, "_filament_ledger_totals", None)
        if cached is None:
            row = obj.adjustments.aggregate(count=Count("id"), balance=Sum("grams"))
            cached = {
                "count": row["count"] or 0,
                "balance": row["balance"] or Decimal("0.00"),
            }
            obj._filament_ledger_totals = cached
        return cached

    def validate(self, attrs):
        makerspace_id = attrs.get("makerspace_id") or getattr(
            self.instance, "makerspace_id", None
        )
        printer = attrs["printer"] if "printer" in attrs else getattr(
            self.instance, "printer", None
        )
        if not makerspace_id:
            raise serializers.ValidationError({"makerspace": "This field is required."})
        if not Makerspace.objects.filter(pk=makerspace_id).exists():
            raise serializers.ValidationError({"makerspace": "Unknown makerspace."})
        if printer and printer.makerspace_id != makerspace_id:
            raise serializers.ValidationError(
                {"printer": "Printer must belong to the same makerspace."}
            )
        remaining = attrs.get(
            "remaining_weight_grams",
            getattr(self.instance, "remaining_weight_grams", None),
        )
        initial = attrs.get(
            "initial_weight_grams",
            getattr(self.instance, "initial_weight_grams", None),
        )
        if initial is not None and remaining is not None and remaining > initial:
            raise serializers.ValidationError(
                {"remaining_weight_grams": "Remaining weight cannot exceed initial weight."}
            )
        return attrs

    def create(self, validated_data):
        makerspace_id = validated_data.pop("makerspace_id")
        return FilamentSpool.objects.create(
            makerspace_id=makerspace_id,
            **validated_data,
        )

    def update(self, instance, validated_data):
        with transaction.atomic():
            locked = FilamentSpool.objects.select_for_update().get(pk=instance.pk)
            update_fields = []
            if "makerspace_id" in validated_data:
                locked.makerspace_id = validated_data.pop("makerspace_id")
                update_fields.append("makerspace")
            for attr, value in validated_data.items():
                setattr(locked, attr, value)
                update_fields.append(attr)
            if update_fields:
                update_fields.append("updated_at")
                locked.save(update_fields=update_fields)
            return locked


class FilamentAdjustmentRequestSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(
        choices=(
            (FilamentAdjustment.Kind.CORRECTION, "Correction"),
            (FilamentAdjustment.Kind.RETIRE, "Retire"),
        )
    )
    grams = serializers.DecimalField(max_digits=10, decimal_places=2)
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)


class FilamentAdjustmentSerializer(serializers.ModelSerializer):
    filament_spool = serializers.IntegerField(source="filament_spool_id", read_only=True)
    makerspace = serializers.IntegerField(source="makerspace_id", read_only=True)
    print_request = serializers.IntegerField(source="print_request_id", read_only=True, allow_null=True)
    manual_log = serializers.IntegerField(source="manual_log_id", read_only=True, allow_null=True)
    created_by = serializers.IntegerField(source="created_by_id", read_only=True, allow_null=True)

    class Meta:
        model = FilamentAdjustment
        fields = (
            "id",
            "filament_spool",
            "makerspace",
            "kind",
            "grams",
            "print_request",
            "manual_log",
            "reason",
            "created_by",
            "created_at",
        )
        read_only_fields = fields


class FilamentAdjustmentResponseSerializer(serializers.Serializer):
    spool = FilamentSpoolSerializer()
    adjustment = FilamentAdjustmentSerializer()
