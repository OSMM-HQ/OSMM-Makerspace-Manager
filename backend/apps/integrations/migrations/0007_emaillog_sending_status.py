from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0006_rename_integration_makers_2fcfc9_idx_integration_makersp_8c1f8c_idx"),
    ]

    operations = [
        migrations.AlterField(
            model_name="emaillog",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("sending", "Sending"),
                    ("sent", "Sent"),
                    ("failed", "Failed"),
                ],
                default="pending",
                max_length=8,
            ),
        ),
    ]
