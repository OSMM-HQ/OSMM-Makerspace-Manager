from django.conf import settings
import django.db.models.deletion
from django.core.validators import RegexValidator
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("payments", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(name="Payment", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("subject_type", models.CharField(choices=[("machine_service_request", "Machine service request")], max_length=48)),
            ("subject_id", models.PositiveBigIntegerField()), ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
            ("currency", models.CharField(max_length=3, validators=[RegexValidator(message="Default currency must be a three-letter lowercase ISO currency code.", regex="^[a-z]{3}$")])),
            ("status", models.CharField(choices=[("pending", "Pending"), ("paid_online", "Paid online"), ("paid_offline", "Paid offline"), ("waived", "Waived"), ("canceled", "Canceled")], default="pending", max_length=16)),
            ("stripe_checkout_session_id", models.CharField(blank=True, max_length=255, null=True, unique=True)),
            ("stripe_checkout_url", models.URLField(blank=True, default="")),
            ("stripe_payment_intent_id", models.CharField(blank=True, max_length=255, null=True, unique=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_payments", to="accounts.user")),
            ("makerspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="makerspaces.makerspace")),
            ("member", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="accounts.user")),
        ], options={"ordering": ["-created_at"]}),
        migrations.CreateModel(name="ProcessedStripeEvent", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("stripe_event_id", models.CharField(max_length=255)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("makerspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="processed_stripe_events", to="makerspaces.makerspace")),
        ]),
        migrations.AddConstraint(model_name="payment", constraint=models.UniqueConstraint(fields=("makerspace", "subject_type", "subject_id"), name="payment_one_per_subject")),
        migrations.AddConstraint(model_name="payment", constraint=models.CheckConstraint(condition=Q(("amount__gt", 0)), name="payment_amount_positive")),
        migrations.AddConstraint(model_name="processedstripeevent", constraint=models.UniqueConstraint(fields=("makerspace", "stripe_event_id"), name="stripe_event_once_per_makerspace")),
        migrations.RunSQL(
            """CREATE OR REPLACE FUNCTION payments_payment_terminal_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' AND current_setting('app.allow_immutable_delete', true) = 'on' THEN RETURN OLD; END IF;
  IF TG_OP = 'UPDATE' AND OLD.status <> 'pending' AND (NEW.status <> OLD.status OR NEW.amount <> OLD.amount) THEN RAISE EXCEPTION 'terminal payment is immutable'; END IF;
  RETURN COALESCE(NEW, OLD);
END; $$;
CREATE TRIGGER payments_payment_terminal_guard BEFORE UPDATE OR DELETE ON payments_payment FOR EACH ROW EXECUTE FUNCTION payments_payment_terminal_guard();""",
            "DROP TRIGGER IF EXISTS payments_payment_terminal_guard ON payments_payment; DROP FUNCTION IF EXISTS payments_payment_terminal_guard();",
        ),
    ]



