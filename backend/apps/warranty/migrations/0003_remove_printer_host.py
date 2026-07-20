from django.db import migrations, models


def assert_warranties_are_machine_hosted(apps, schema_editor):
    Warranty = apps.get_model("warranty", "Warranty")
    if Warranty.objects.exclude(printer_id=None).exists():
        raise RuntimeError("Cannot remove Warranty.printer while printer-hosted warranties remain.")


class Migration(migrations.Migration):
    dependencies = [
        ("warranty", "0002_machine_host"),
        ("machines", "0014_preservable_historical_ledger_timestamps"),
    ]

    operations = [
        migrations.RunPython(assert_warranties_are_machine_hosted, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="warranty", name="warranty_exactly_one_host"),
        migrations.RemoveField(model_name="warranty", name="printer"),
        migrations.AddConstraint(
            model_name="warranty",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(asset__isnull=False, machine__isnull=True)
                    | models.Q(asset__isnull=True, machine__isnull=False)
                ),
                name="warranty_exactly_one_host",
            ),
        ),
    ]
