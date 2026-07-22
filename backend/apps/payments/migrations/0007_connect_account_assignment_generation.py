from django.db import migrations, models


def backfill_assignment_generation(apps, schema_editor):
    payment_settings = apps.get_model("payments", "MakerspacePaymentSettings")
    payment_settings.objects.filter(
        connect_account_id__isnull=False,
        connect_account_assigned_at__isnull=True,
    ).update(connect_account_assigned_at=models.F("connect_status_updated_at"))


class Migration(migrations.Migration):
    dependencies = [("payments", "0006_payment_checkout_expiry_confirmation")]

    operations = [
        migrations.AddField(
            model_name="makerspacepaymentsettings",
            name="connect_account_assigned_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_assignment_generation, migrations.RunPython.noop),
    ]
