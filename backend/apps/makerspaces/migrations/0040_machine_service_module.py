from django.db import migrations


MODULE = "machine_service"


def enable_machine_service(apps, schema_editor):
    Makerspace = apps.get_model("makerspaces", "Makerspace")
    for makerspace in Makerspace.objects.all().iterator():
        modules = list(makerspace.enabled_modules or [])
        if MODULE not in modules:
            modules.append(MODULE)
            makerspace.enabled_modules = modules
            makerspace.save(update_fields=["enabled_modules"])


def disable_machine_service(apps, schema_editor):
    Makerspace = apps.get_model("makerspaces", "Makerspace")
    for makerspace in Makerspace.objects.all().iterator():
        modules = [module for module in (makerspace.enabled_modules or []) if module != MODULE]
        makerspace.enabled_modules = modules
        makerspace.save(update_fields=["enabled_modules"])


class Migration(migrations.Migration):
    dependencies = [("makerspaces", "0039_seed_and_backfill_roles")]

    operations = [migrations.RunPython(enable_machine_service, disable_machine_service)]
