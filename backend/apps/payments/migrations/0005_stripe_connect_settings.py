import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0004_payment_delete_immutability"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="makerspacepaymentsettings",
            name="stripe_publishable_key",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="makerspacepaymentsettings",
            name="connect_account_id",
            field=models.CharField(blank=True, max_length=255, null=True, unique=True, validators=[django.core.validators.RegexValidator(message="Enter a valid Stripe connected account ID.", regex="^acct_[A-Za-z0-9]+$")]),
        ),
        migrations.AddField(model_name="makerspacepaymentsettings", name="connect_charges_enabled", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="makerspacepaymentsettings", name="connect_payouts_enabled", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="makerspacepaymentsettings", name="connect_status", field=models.CharField(choices=[("unconnected", "Unconnected"), ("pending", "Pending"), ("active", "Active"), ("restricted", "Restricted"), ("disconnected", "Disconnected")], default="unconnected", max_length=16)),
        migrations.AddField(model_name="makerspacepaymentsettings", name="connect_status_updated_at", field=models.DateTimeField(default=django.utils.timezone.now)),
        migrations.AddField(model_name="payment", name="stripe_application_fee_amount", field=models.PositiveBigIntegerField(default=0)),
        migrations.AddField(model_name="payment", name="stripe_connected_account_id", field=models.CharField(blank=True, max_length=255, null=True)),
        migrations.AddField(model_name="payment", name="stripe_provider", field=models.CharField(choices=[("raw", "Makerspace raw credentials"), ("connect", "Stripe Connect")], default="raw", max_length=16)),
        migrations.CreateModel(
            name="PlatformStripeConnectSettings",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ("stripe_publishable_key", models.CharField(blank=True, default="", max_length=255)),
                ("stripe_secret_key", models.TextField(blank=True, default="")),
                ("stripe_webhook_secret", models.TextField(blank=True, default="")),
                ("stripe_connect_client_id", models.CharField(blank=True, default="", max_length=255)),
                ("application_fee_bps", models.PositiveSmallIntegerField(default=0, validators=[django.core.validators.MaxValueValidator(10000)])),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="StripeConnectOAuthState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("state_digest", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("initiated_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("makerspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stripe_connect_oauth_states", to="makerspaces.makerspace")),
            ],
        ),
    ]
