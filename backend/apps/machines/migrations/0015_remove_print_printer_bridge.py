from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("machines", "0014_preservable_historical_ledger_timestamps"),
        ("procurement", "0006_kernel_printing_references"),
        ("warranty", "0003_remove_printer_host"),
    ]

    operations = [
        migrations.RemoveField(model_name="machine", name="linked_print_printer"),
    ]
