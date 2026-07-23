from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("encryption", "0001_initial"), ("events", "0003_custom_forms_structured_location")]
    operations = [
        migrations.AlterField(model_name="eventregistration", name="name", field=models.TextField()),
        migrations.AlterField(model_name="eventregistration", name="email", field=models.TextField()),
        migrations.AlterField(model_name="eventregistration", name="phone", field=models.TextField()),
    ]
