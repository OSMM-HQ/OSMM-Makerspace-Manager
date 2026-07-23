from django.db import migrations


PRINTER_CONFIG = {
    "schema": "3d-printer-v1",
    "service_payload_schema": "printer-v1",
    "machine_payload_schema": "printer-machine-v1",
    "accepted_materials": ["PLA", "PETG", "TPU"],
    "accepted_colours": ["Black", "Blue", "Green", "Red", "White", "Gray"],
    "metering_unit": "weight",
    "pooled_service_queue": True,
    "typed_consumable_pools": True,
    "service_file_policy": {"name": "printer", "version": 1},
    "printer_hours": True,
    "run_sheet_required": True,
}

PACKS = {
    "resin_printer": {"metering_unit": "volume", "requires_booking": False, "pooled_service_queue": True, "typed_consumable_pools": True, "pool_unit": "milliliters", "consumable": "resin"},
    "laser_cutter": {"metering_unit": "minutes", "requires_booking": True},
    "cnc_router": {"metering_unit": "minutes", "requires_booking": True},
    "vinyl_cutter": {"metering_unit": "length", "requires_booking": False, "pooled_service_queue": True, "pool_unit": "millimeters"},
}


def forward(apps, schema_editor):
    MachineType = apps.get_model("machines", "MachineType")
    # Preserve any deployment customization (e.g. accepted_materials/colours) —
    # only make the structural change: drop the obsolete payment flag and add the
    # metering unit. Fall back to defaults only if the row somehow has no config.
    for printer in MachineType.objects.filter(makerspace__isnull=True, slug="3d_printer"):
        config = dict(printer.capability_config or {})
        if not config:
            config = dict(PRINTER_CONFIG)
        else:
            config.pop("payment_enabled", None)
            config["metering_unit"] = "weight"
        MachineType.objects.filter(pk=printer.pk).update(capability_config=config)
    for slug, config in PACKS.items():
        MachineType.objects.update_or_create(
            makerspace_id=None, slug=slug,
            defaults={"name": slug.replace("_", " ").title(), "icon": "", "is_builtin": True, "managing_action": "", "capability_config": config},
        )


class Migration(migrations.Migration):
    dependencies = [("machines", "0016_machine_metering_generalization")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
