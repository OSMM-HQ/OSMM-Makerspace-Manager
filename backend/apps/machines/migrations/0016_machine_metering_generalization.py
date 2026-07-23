from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("machines", "0015_remove_print_printer_bridge")]

    operations = [
        migrations.AddField(
            model_name="machineconsumablepool",
            name="unit",
            field=models.CharField(choices=[("grams", "Grams"), ("milliliters", "Milliliters"), ("millimeters", "Millimeters"), ("count", "Count")], default="grams", max_length=12),
        ),
        migrations.AddField(
            model_name="machineconsumableadjustment",
            name="metering_unit",
            field=models.CharField(choices=[("minutes", "Minutes"), ("weight", "Weight"), ("volume", "Volume"), ("length", "Length"), ("count", "Count")], default="weight", max_length=12),
        ),
        migrations.AddField(
            model_name="machineconsumableadjustment",
            name="consumed_quantity",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="machineusageentry",
            name="metering_unit",
            field=models.CharField(choices=[("minutes", "Minutes"), ("weight", "Weight"), ("volume", "Volume"), ("length", "Length"), ("count", "Count")], default="weight", max_length=12),
        ),
        migrations.AddField(
            model_name="machineusageentry",
            name="consumed_quantity",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="machineservicerequest",
            name="metering_unit",
            field=models.CharField(blank=True, choices=[("minutes", "Minutes"), ("weight", "Weight"), ("volume", "Volume"), ("length", "Length"), ("count", "Count")], max_length=12, null=True),
        ),
        migrations.AddField(
            model_name="machineservicerequest",
            name="planned_quantity",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="machineservicerequest",
            name="reserved_quantity",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="machineservicerequest",
            name="actual_consumed_quantity",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE machines_machineconsumableadjustment DISABLE TRIGGER machine_consumable_adjustment_no_update;
                ALTER TABLE machines_machineusageentry DISABLE TRIGGER machine_usage_entry_no_update;
                UPDATE machines_machineconsumableadjustment SET consumed_quantity = quantity_delta;
                UPDATE machines_machineusageentry SET consumed_quantity = consumed_grams;
                ALTER TABLE machines_machineconsumableadjustment ENABLE TRIGGER machine_consumable_adjustment_no_update;
                ALTER TABLE machines_machineusageentry ENABLE TRIGGER machine_usage_entry_no_update;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddConstraint(
            model_name="machineusageentry",
            constraint=models.CheckConstraint(condition=models.Q(("consumed_quantity__gte", 0)), name="machineusage_quantity_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="machineservicerequest",
            constraint=models.CheckConstraint(condition=models.Q(("planned_quantity__isnull", True), ("planned_quantity__gte", 0), _connector="OR"), name="service_req_planned_quantity_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="machineservicerequest",
            constraint=models.CheckConstraint(condition=models.Q(("reserved_quantity__isnull", True), ("reserved_quantity__gte", 0), _connector="OR"), name="service_req_reserved_quantity_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="machineservicerequest",
            constraint=models.CheckConstraint(condition=models.Q(("actual_consumed_quantity__isnull", True), ("actual_consumed_quantity__gte", 0), _connector="OR"), name="service_req_actual_quantity_nonnegative"),
        ),
    ]
