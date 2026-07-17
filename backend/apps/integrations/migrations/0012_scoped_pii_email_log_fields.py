from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("encryption", "0001_initial"), ("integrations", "0011_dailynotificationcounter_notificationdeliverylog_and_more")]
    operations = [
        migrations.AlterField(model_name="emaillog", name="to_email", field=models.TextField()),
        migrations.AlterField(model_name="emaillog", name="subject", field=models.TextField()),
    ]
