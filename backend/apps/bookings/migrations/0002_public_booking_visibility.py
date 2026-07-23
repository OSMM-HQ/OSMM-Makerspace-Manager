from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='bookablespace',
            name='show_public_availability',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='bookablespace',
            name='show_public_booker_names',
            field=models.BooleanField(default=False),
        ),
    ]
