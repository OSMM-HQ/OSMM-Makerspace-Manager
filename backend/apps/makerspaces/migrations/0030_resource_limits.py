from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("makerspaces", "0029_reconcile_selfhost_domains"),
    ]

    operations = [
        migrations.AddField(
            model_name="makerspace",
            name="resource_limit_overrides",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="makerspace",
            name="storage_bytes_used",
            field=models.BigIntegerField(default=0),
        ),
    ]
