from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("bookings", "0006_member_ownership")]

    operations = [
        migrations.AddField(
            model_name="bookablespace",
            name="payment_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
                validators=[MinValueValidator(0)],
            ),
        ),
        migrations.AddConstraint(
            model_name="bookablespace",
            constraint=models.CheckConstraint(
                condition=models.Q(("payment_amount__gte", 0)),
                name="bookspace_payment_nonnegative",
            ),
        ),
    ]
