from django.db import migrations

import apps.machines.model_fields


class Migration(migrations.Migration):
    dependencies = [("machines", "0013_printing_kernel_cutover_provenance")]

    operations = [
        migrations.AlterField(
            model_name="machineconsumableadjustment",
            name="created_at",
            field=apps.machines.model_fields.PreservableCreatedAtField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="machineusageentry",
            name="created_at",
            field=apps.machines.model_fields.PreservableCreatedAtField(auto_now_add=True),
        ),
    ]
