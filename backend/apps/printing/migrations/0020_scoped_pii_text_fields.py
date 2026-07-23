from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("encryption", "0001_initial"), ("printing", "0019_filament_adjustment")]
    operations = [
        migrations.AlterField(model_name="printrequest", name="requester_name", field=models.TextField(blank=True)),
        migrations.AlterField(model_name="printrequest", name="contact_email", field=models.TextField(blank=True)),
        migrations.AlterField(model_name="printrequest", name="contact_phone", field=models.TextField(blank=True)),
        migrations.AlterField(model_name="manualprintlog", name="requester_name", field=models.TextField(blank=True, default="")),
        migrations.AlterField(model_name="manualprintlog", name="contact_email", field=models.TextField(blank=True, default="")),
        migrations.AlterField(model_name="manualprintlog", name="contact_phone", field=models.TextField(blank=True, default="")),
    ]
