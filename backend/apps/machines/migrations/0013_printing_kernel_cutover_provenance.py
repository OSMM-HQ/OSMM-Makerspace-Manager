# Generated for the B4 forward-only printing cutover.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("machines", "0012_printer_machine_type_configuration"),
        ("printing", "0021_member_owned_public_uploads"),
    ]

    operations = [
        migrations.AddField(model_name="machine", name="legacy_print_printer_id", field=models.PositiveIntegerField(blank=True, editable=False, null=True, unique=True)),
        migrations.AddField(model_name="servicequeue", name="legacy_print_bucket_id", field=models.PositiveIntegerField(blank=True, editable=False, null=True, unique=True)),
        migrations.AddField(model_name="machineservicerequest", name="legacy_print_request_id", field=models.PositiveIntegerField(blank=True, editable=False, null=True, unique=True)),
        migrations.AddField(model_name="servicerequestfile", name="legacy_print_request_file_id", field=models.PositiveIntegerField(blank=True, editable=False, null=True, unique=True)),
        migrations.AddField(model_name="machineconsumablepool", name="legacy_filament_spool_id", field=models.PositiveIntegerField(blank=True, editable=False, null=True, unique=True)),
        migrations.AddField(model_name="machineconsumableadjustment", name="legacy_filament_adjustment_id", field=models.PositiveIntegerField(blank=True, editable=False, null=True, unique=True)),
        migrations.AddField(model_name="machineusageentry", name="legacy_manual_print_log_id", field=models.PositiveIntegerField(blank=True, editable=False, null=True, unique=True)),
        migrations.AddField(model_name="machineusageentry", name="title", field=models.CharField(blank=True, max_length=200)),
        migrations.AddField(model_name="machineusageentry", name="requester_name", field=models.TextField(blank=True)),
        migrations.AddField(model_name="machineusageentry", name="contact_email", field=models.TextField(blank=True)),
        migrations.AddField(model_name="machineusageentry", name="contact_phone", field=models.TextField(blank=True)),
        migrations.CreateModel(
            name="PrintingCutoverState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kernel_authoritative_at", models.DateTimeField(blank=True, null=True)),
                ("reconciled_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("makerspace", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="printing_cutover_state", to="makerspaces.makerspace")),
            ],
        ),
        migrations.CreateModel(
            name="PrintingCutoverRepair",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("invalid_source", "Invalid legacy source"), ("mismatch", "Reconciliation mismatch"), ("missing_object", "Missing storage object"), ("collision", "Provenance/object collision"), ("warranty", "Unmapped warranty link")], max_length=32)),
                ("legacy_model", models.CharField(max_length=100)),
                ("legacy_id", models.PositiveIntegerField(blank=True, null=True)),
                ("detail", models.JSONField(blank=True, default=dict)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("makerspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="printing_cutover_repairs", to="makerspaces.makerspace")),
                ("resolved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.AddConstraint(model_name="printingcutoverrepair", constraint=models.UniqueConstraint(fields=("makerspace", "kind", "legacy_model", "legacy_id"), name="uniq_print_cutover_repair_source")),
    ]
