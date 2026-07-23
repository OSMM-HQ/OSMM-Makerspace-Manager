from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("payments", "0003_backfill_legacy_machine_payments")]

    operations = [
        migrations.RunSQL(
            """CREATE OR REPLACE FUNCTION payments_payment_terminal_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF current_setting('app.allow_immutable_delete', true) = 'on' THEN RETURN OLD; END IF;
    RAISE EXCEPTION 'payment is immutable';
  END IF;
  IF TG_OP = 'UPDATE' AND OLD.status <> 'pending' AND (NEW.status <> OLD.status OR NEW.amount <> OLD.amount) THEN
    RAISE EXCEPTION 'terminal payment is immutable';
  END IF;
  RETURN COALESCE(NEW, OLD);
END; $$;""",
            """CREATE OR REPLACE FUNCTION payments_payment_terminal_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' AND current_setting('app.allow_immutable_delete', true) = 'on' THEN RETURN OLD; END IF;
  IF TG_OP = 'UPDATE' AND OLD.status <> 'pending' AND (NEW.status <> OLD.status OR NEW.amount <> OLD.amount) THEN RAISE EXCEPTION 'terminal payment is immutable'; END IF;
  RETURN COALESCE(NEW, OLD);
END; $$;""",
        ),
    ]
