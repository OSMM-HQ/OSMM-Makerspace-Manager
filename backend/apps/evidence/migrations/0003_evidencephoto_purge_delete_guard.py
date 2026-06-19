from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("evidence", "0002_evidencephoto_immutable_triggers"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
CREATE OR REPLACE FUNCTION evidence_reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('app.allow_immutable_delete', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'append-only/immutable table: % not allowed', TG_OP;
END;
$$;
""",
            reverse_sql="""
CREATE OR REPLACE FUNCTION evidence_reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'append-only/immutable table: % not allowed', TG_OP;
END;
$$;
""",
        ),
    ]
