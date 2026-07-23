from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("encryption", "0001_initial"), ("bookings", "0004_bookablespace_booking_rules")]
    operations = [
        migrations.AlterField(model_name="booking", name="name", field=models.TextField()),
        migrations.AlterField(model_name="booking", name="email", field=models.TextField()),
        migrations.AlterField(model_name="booking", name="phone", field=models.TextField()),
    ]
