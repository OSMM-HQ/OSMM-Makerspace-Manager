from django.db import migrations


def _status_for(printer):
    if not printer.is_active or printer.status == "offline":
        return "offline"
    if printer.status == "maintenance":
        return "maintenance"
    return "idle"


def backfill(apps, schema_editor):
    # Create one linked Machine per existing PrintPrinter (idempotent). New printers
    # get linked by the post_save signal; this covers rows created before the app.
    PrintPrinter = apps.get_model("printing", "PrintPrinter")
    Machine = apps.get_model("machines", "Machine")
    MachineType = apps.get_model("machines", "MachineType")

    machine_type = MachineType.objects.filter(
        makerspace__isnull=True, slug="3d_printer"
    ).first()
    if machine_type is None:
        return

    for printer in PrintPrinter.objects.all():
        if printer.makerspace_id is None:
            continue
        if Machine.objects.filter(linked_print_printer=printer).exists():
            continue
        Machine.objects.create(
            makerspace_id=printer.makerspace_id,
            machine_type=machine_type,
            linked_print_printer=printer,
            name=getattr(printer, "name", "") or f"Printer {printer.pk}",
            status=_status_for(printer),
            is_active=True,
        )


def unbackfill(apps, schema_editor):
    Machine = apps.get_model("machines", "Machine")
    Machine.objects.filter(linked_print_printer__isnull=False).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("machines", "0002_seed_builtin_machine_types"),
        ("printing", "0019_filament_adjustment"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
