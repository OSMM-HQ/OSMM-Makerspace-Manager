from django.db import migrations

# Global built-in machine types (makerspace=NULL, is_builtin=True). Only the
# 3d_printer row carries a managing_action so the existing Print Manager
# (Action.MANAGE_PRINTING) can manage 3d_printer machines; other types get no
# type-manager role in M1. Stored as the rbac.Action VALUE so it can be passed
# straight to rbac.can(actor, managing_action, makerspace_id).
BUILTINS = [
    ("3d_printer", "3D Printer", "manage_printing"),
    ("laser_cutter", "Laser Cutter", ""),
    ("cnc_mill", "CNC Mill", ""),
    ("cnc_router", "CNC Router", ""),
    ("vinyl_cutter", "Vinyl Cutter", ""),
    ("pcb_mill", "PCB Milling Machine", ""),
    ("other", "Other", ""),
]


def seed_builtins(apps, schema_editor):
    MachineType = apps.get_model("machines", "MachineType")
    for slug, name, managing_action in BUILTINS:
        MachineType.objects.get_or_create(
            slug=slug,
            makerspace=None,
            defaults={
                "name": name,
                "is_builtin": True,
                "managing_action": managing_action,
            },
        )


def unseed_builtins(apps, schema_editor):
    MachineType = apps.get_model("machines", "MachineType")
    slugs = [slug for slug, _, _ in BUILTINS]
    MachineType.objects.filter(makerspace__isnull=True, slug__in=slugs).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("machines", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_builtins, unseed_builtins),
    ]
