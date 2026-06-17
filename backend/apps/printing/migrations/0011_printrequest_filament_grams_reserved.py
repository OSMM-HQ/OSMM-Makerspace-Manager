import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("printing", "0010_manualprintlog_grams_positive"),
    ]

    operations = [
        migrations.AddField(
            model_name="printrequest",
            name="filament_grams_reserved",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=8,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
    ]
