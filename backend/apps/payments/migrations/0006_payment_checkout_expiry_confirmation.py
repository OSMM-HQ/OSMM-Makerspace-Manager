from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("payments", "0005_stripe_connect_settings")]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="stripe_checkout_session_expired_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
