from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0007_emaillog_sending_status"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="emaillog",
            index=models.Index(
                fields=["makerspace", "status", "-created_at"],
                name="integration_emaill_makersp_8c9fd1_idx",
            ),
        ),
    ]
