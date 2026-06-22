from rest_framework import serializers


class PrintingReportTotalsSerializer(serializers.Serializer):
    total_requests = serializers.IntegerField()
    completed = serializers.IntegerField()
    collected = serializers.IntegerField()
    failed = serializers.IntegerField()
    rejected = serializers.IntegerField()
    pending = serializers.IntegerField()
    printing = serializers.IntegerField()
    accepted = serializers.IntegerField()


class PrintingReportPrinterHoursSerializer(serializers.Serializer):
    printer_id = serializers.IntegerField()
    printer_name = serializers.CharField()
    image_url = serializers.URLField(required=False, allow_null=True)
    completed_requests = serializers.IntegerField()
    hours = serializers.FloatField()
    makerspace_id = serializers.IntegerField(required=False)


class PrintingReportPrinterOutcomeSerializer(serializers.Serializer):
    printer_id = serializers.IntegerField()
    printer_name = serializers.CharField()
    image_url = serializers.URLField(required=False, allow_null=True)
    completed = serializers.IntegerField()
    failed = serializers.IntegerField()
    grams_used = serializers.FloatField(
        help_text=(
            "Per-printer request-outcome grams. Completed print requests use the "
            "estimate reconciled at completion; manual print-log grams are added "
            "on this axis. This is not a measured actual for completed requests."
        )
    )
    manual_logs = serializers.IntegerField()
    makerspace_id = serializers.IntegerField(required=False)


class PrintingReportFilamentUsedSerializer(serializers.Serializer):
    spool_id = serializers.IntegerField()
    material = serializers.CharField()
    color = serializers.CharField(allow_blank=True)
    grams_used = serializers.FloatField(
        help_text=(
            "Per-spool inventory delta: initial weight minus remaining weight. "
            "Manual print logs already affect this total when they decrement a spool."
        )
    )
    remaining_grams = serializers.FloatField()
    makerspace_id = serializers.IntegerField(required=False)


class PrintingReportPeriodSerializer(serializers.Serializer):
    period = serializers.CharField()
    grams = serializers.FloatField(
        help_text="Estimated filament grams for completed print requests in this period."
    )


class PrintingReportPeriodsSerializer(serializers.Serializer):
    by_month = PrintingReportPeriodSerializer(many=True)
    by_day = PrintingReportPeriodSerializer(many=True)
    by_hour = PrintingReportPeriodSerializer(many=True)


class PrintingReportBrandSerializer(serializers.Serializer):
    brand = serializers.CharField()
    grams_used = serializers.FloatField(
        help_text=(
            "Brand-level spool inventory delta: initial weight minus remaining weight."
        )
    )
    spools = serializers.IntegerField()


class PrintingReportTopRequesterSerializer(serializers.Serializer):
    requester_id = serializers.IntegerField()
    requester = serializers.CharField()
    grams = serializers.FloatField()
    requests = serializers.IntegerField()
    items = serializers.IntegerField()
    makerspace_id = serializers.IntegerField(required=False)


class PrintingReportPaymentsSerializer(serializers.Serializer):
    paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    paid_count = serializers.IntegerField()
    outstanding_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    outstanding_count = serializers.IntegerField()


class PrintingReportSerializer(serializers.Serializer):
    totals = PrintingReportTotalsSerializer()
    printer_hours = PrintingReportPrinterHoursSerializer(many=True)
    printer_outcomes = PrintingReportPrinterOutcomeSerializer(
        many=True,
        help_text=(
            "Per-printer request-outcome axis. Completed request grams are "
            "estimate-based; manual print logs are added as printer activity."
        ),
    )
    filament_used = PrintingReportFilamentUsedSerializer(
        many=True,
        help_text=(
            "Per-spool inventory-delta axis. These values are independent of the "
            "per-printer request-outcome aggregation."
        ),
    )
    filament_by_brand = PrintingReportBrandSerializer(many=True)
    top_requesters = PrintingReportTopRequesterSerializer(many=True)
    total_grams_used = serializers.FloatField(
        help_text=(
            "Total spool inventory delta across included spools, not a sum of "
            "completed-request estimates."
        )
    )
    payments = PrintingReportPaymentsSerializer()
    filament_estimated_by_period = PrintingReportPeriodsSerializer(
        help_text="Completed-request filament estimates grouped by completion period."
    )
