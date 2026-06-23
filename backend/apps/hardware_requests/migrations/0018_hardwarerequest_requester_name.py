from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hardware_requests", "0017_remove_hardwareemailtemplate"),
    ]

    operations = [
        migrations.AddField(
            model_name="hardwarerequest",
            name="requester_name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
    ]
