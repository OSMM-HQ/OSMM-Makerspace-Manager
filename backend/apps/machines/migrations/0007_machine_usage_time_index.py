from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("machines", "0006_machine_is_public")]

    operations = [
        migrations.AddIndex(
            model_name="machineusageentry",
            index=models.Index(fields=["machine", "created_at"], name="usage_machine_created_idx"),
        ),
    ]
