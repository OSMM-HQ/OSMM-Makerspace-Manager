from django.core.validators import MinValueValidator
from django.db import migrations, models


def enable_membership(apps, schema_editor):
    Makerspace = apps.get_model("makerspaces", "Makerspace")
    for makerspace in Makerspace.objects.order_by("id").iterator():
        modules = list(makerspace.enabled_modules or [])
        if "membership" not in modules:
            modules.append("membership")
            makerspace.enabled_modules = modules
            makerspace.save(update_fields=["enabled_modules"])


class Migration(migrations.Migration):
    dependencies = [("makerspaces", "0048_makerspace_geofence")]

    operations = [
        migrations.AddField(
            model_name="makerspace",
            name="membership_dues_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
                validators=[MinValueValidator(0)],
            ),
        ),
        migrations.AddConstraint(
            model_name="makerspace",
            constraint=models.CheckConstraint(
                condition=models.Q(("membership_dues_amount__gte", 0)),
                name="makerspace_dues_nonnegative",
            ),
        ),
        migrations.RunPython(enable_membership, migrations.RunPython.noop),
    ]
