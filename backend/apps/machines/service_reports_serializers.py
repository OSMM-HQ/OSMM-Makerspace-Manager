from rest_framework import serializers


class _ScopedSerializer(serializers.Serializer):
    makerspace_id = serializers.IntegerField(required=False)


class MachineServiceStatusTotalsSerializer(_ScopedSerializer):
    submitted = serializers.IntegerField()
    accepted = serializers.IntegerField()
    in_progress = serializers.IntegerField()
    completed = serializers.IntegerField()
    collected = serializers.IntegerField()
    rejected = serializers.IntegerField()
    failed = serializers.IntegerField()


class MachineServiceMachineSerializer(_ScopedSerializer):
    machine_id = serializers.IntegerField()
    machine_name = serializers.CharField()
    machine_type = serializers.CharField(allow_blank=True, allow_null=True)
    request_count = serializers.IntegerField()
    completed_count = serializers.IntegerField()
    failed_count = serializers.IntegerField()
    completed_hours = serializers.FloatField()
    failed_partial_hours = serializers.FloatField()
    total_recorded_service_hours = serializers.FloatField()
    failure_rate = serializers.FloatField(allow_null=True)


class MachineServiceConsumptionSerializer(_ScopedSerializer):
    machine_id = serializers.IntegerField()
    machine_name = serializers.CharField()
    machine_type = serializers.CharField(allow_blank=True, allow_null=True)
    measurement = serializers.ChoiceField(choices=("count", "grams"))
    product_id = serializers.IntegerField(allow_null=True)
    product_label = serializers.CharField(allow_blank=True)
    completed_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    failed_partial_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_used = serializers.DecimalField(max_digits=12, decimal_places=2)


class MachineServiceFailureSerializer(_ScopedSerializer):
    machine_id = serializers.IntegerField()
    machine_name = serializers.CharField()
    machine_type = serializers.CharField(allow_blank=True, allow_null=True)
    outcome = serializers.CharField()
    failed_count = serializers.IntegerField()
    failed_partial_hours = serializers.FloatField()
    failed_count_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    failed_grams_amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class MachineServiceReportSerializer(serializers.Serializer):
    status_totals = MachineServiceStatusTotalsSerializer(many=True)
    machines = MachineServiceMachineSerializer(many=True)
    consumption = MachineServiceConsumptionSerializer(many=True)
    failure_summary = MachineServiceFailureSerializer(many=True)
