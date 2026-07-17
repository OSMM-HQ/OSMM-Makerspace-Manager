from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("encryption", "0001_initial"), ("hardware_requests", "0022_publicproblemreport_triage_fields")]
    operations = [
        migrations.AlterField(model_name="hardwarerequest", name="requester_username", field=models.TextField()),
        migrations.AlterField(model_name="hardwarerequest", name="requester_name", field=models.TextField(blank=True, default="")),
        migrations.AlterField(model_name="hardwarerequest", name="requester_contact_email", field=models.TextField(blank=True)),
        migrations.AlterField(model_name="hardwarerequest", name="requester_contact_phone", field=models.TextField(blank=True)),
    ]
