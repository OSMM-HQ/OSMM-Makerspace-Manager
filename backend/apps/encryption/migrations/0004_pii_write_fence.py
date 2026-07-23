import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


GLOBAL_NAMESPACE = 734201
TENANT_NAMESPACE = 734202


FENCE_SQL = f"""
CREATE FUNCTION pii_assert_mapped_write_allowed(p_makerspace_id bigint) RETURNS void AS $$
DECLARE global_fence record; tenant_fence record; operation text;
BEGIN
  PERFORM pg_advisory_xact_lock_shared({GLOBAL_NAMESPACE}, 0);
  IF p_makerspace_id IS NOT NULL THEN
    PERFORM pg_advisory_xact_lock_shared({TENANT_NAMESPACE}, p_makerspace_id::integer);
  END IF;
  SELECT state, operation_id, operation_kind INTO global_fence
    FROM encryption_piiglobalwritefence WHERE id = 1;
  IF NOT FOUND THEN RAISE EXCEPTION 'pii write fence missing'; END IF;
  operation := current_setting('app.pii_fence_operation', true);
  IF global_fence.state = 'closed' AND (
    operation IS DISTINCT FROM global_fence.operation_id::text OR
    global_fence.operation_kind NOT IN ('enable_transition', 'decrypt_rollback', 'search_rotation')
  ) THEN RAISE EXCEPTION 'pii write fence closed'; END IF;
  IF p_makerspace_id IS NOT NULL THEN
    SELECT state, operation_id, operation_kind INTO tenant_fence
      FROM encryption_piimakerspacewritefence WHERE makerspace_id = p_makerspace_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'pii write fence missing'; END IF;
    IF tenant_fence.state = 'closed' AND (
      operation IS DISTINCT FROM tenant_fence.operation_id::text OR
      tenant_fence.operation_kind NOT IN ('enable_transition', 'decrypt_rollback', 'search_rotation')
    ) THEN RAISE EXCEPTION 'pii write fence closed'; END IF;
  END IF;
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION pii_fence_hardware_request() RETURNS trigger AS $$
BEGIN PERFORM pii_assert_mapped_write_allowed(NEW.makerspace_id); RETURN NEW; END; $$ LANGUAGE plpgsql;
CREATE FUNCTION pii_fence_print_request() RETURNS trigger AS $$
DECLARE tenant_id bigint;
BEGIN SELECT makerspace_id INTO tenant_id FROM printing_printbucket WHERE id = NEW.bucket_id FOR KEY SHARE;
  PERFORM pii_assert_mapped_write_allowed(tenant_id); RETURN NEW; END; $$ LANGUAGE plpgsql;
CREATE FUNCTION pii_fence_manual_print_log() RETURNS trigger AS $$
BEGIN PERFORM pii_assert_mapped_write_allowed(NEW.makerspace_id); RETURN NEW; END; $$ LANGUAGE plpgsql;
CREATE FUNCTION pii_fence_event_registration() RETURNS trigger AS $$
DECLARE tenant_id bigint;
BEGIN SELECT makerspace_id INTO tenant_id FROM events_event WHERE id = NEW.event_id FOR KEY SHARE;
  PERFORM pii_assert_mapped_write_allowed(tenant_id); RETURN NEW; END; $$ LANGUAGE plpgsql;
CREATE FUNCTION pii_fence_booking() RETURNS trigger AS $$
DECLARE tenant_id bigint;
BEGIN SELECT makerspace_id INTO tenant_id FROM bookings_bookablespace WHERE id = NEW.space_id FOR KEY SHARE;
  PERFORM pii_assert_mapped_write_allowed(tenant_id); RETURN NEW; END; $$ LANGUAGE plpgsql;
CREATE FUNCTION pii_fence_email_log() RETURNS trigger AS $$
BEGIN PERFORM pii_assert_mapped_write_allowed(NEW.makerspace_id); RETURN NEW; END; $$ LANGUAGE plpgsql;

CREATE TRIGGER pii_fence_hardware_request_trigger BEFORE INSERT OR UPDATE OF requester_username, requester_name, requester_contact_email, requester_contact_phone ON hardware_requests_hardwarerequest FOR EACH ROW EXECUTE FUNCTION pii_fence_hardware_request();
CREATE TRIGGER pii_fence_print_request_trigger BEFORE INSERT OR UPDATE OF requester_name, contact_email, contact_phone ON printing_printrequest FOR EACH ROW EXECUTE FUNCTION pii_fence_print_request();
CREATE TRIGGER pii_fence_manual_print_log_trigger BEFORE INSERT OR UPDATE OF requester_name, contact_email, contact_phone, note ON printing_manualprintlog FOR EACH ROW EXECUTE FUNCTION pii_fence_manual_print_log();
CREATE TRIGGER pii_fence_event_registration_trigger BEFORE INSERT OR UPDATE OF name, email, phone ON events_eventregistration FOR EACH ROW EXECUTE FUNCTION pii_fence_event_registration();
CREATE TRIGGER pii_fence_booking_trigger BEFORE INSERT OR UPDATE OF name, email, phone, note ON bookings_booking FOR EACH ROW EXECUTE FUNCTION pii_fence_booking();
CREATE TRIGGER pii_fence_email_log_trigger BEFORE INSERT OR UPDATE OF to_email, subject, text_body, html_body ON integrations_emaillog FOR EACH ROW EXECUTE FUNCTION pii_fence_email_log();

CREATE FUNCTION encryption_prevent_pii_fence_delete() RETURNS trigger AS $$
BEGIN
  IF current_setting('app.allow_immutable_delete', true) = 'on' THEN RETURN OLD; END IF;
  RAISE EXCEPTION 'PII write-fence rows cannot be deleted';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER encryption_prevent_pii_makerspace_fence_delete
BEFORE DELETE ON encryption_piimakerspacewritefence
FOR EACH ROW EXECUTE FUNCTION encryption_prevent_pii_fence_delete();

CREATE FUNCTION encryption_prevent_pii_global_fence_delete() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'PII global write-fence row cannot be deleted'; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER encryption_prevent_pii_global_fence_delete
BEFORE DELETE ON encryption_piiglobalwritefence
FOR EACH ROW EXECUTE FUNCTION encryption_prevent_pii_global_fence_delete();
"""


REVERSE_FENCE_SQL = """
DROP TRIGGER IF EXISTS encryption_prevent_pii_makerspace_fence_delete ON encryption_piimakerspacewritefence;
DROP FUNCTION IF EXISTS encryption_prevent_pii_fence_delete();
DROP TRIGGER IF EXISTS encryption_prevent_pii_global_fence_delete ON encryption_piiglobalwritefence;
DROP FUNCTION IF EXISTS encryption_prevent_pii_global_fence_delete();
DROP TRIGGER IF EXISTS pii_fence_hardware_request_trigger ON hardware_requests_hardwarerequest;
DROP TRIGGER IF EXISTS pii_fence_print_request_trigger ON printing_printrequest;
DROP TRIGGER IF EXISTS pii_fence_manual_print_log_trigger ON printing_manualprintlog;
DROP TRIGGER IF EXISTS pii_fence_event_registration_trigger ON events_eventregistration;
DROP TRIGGER IF EXISTS pii_fence_booking_trigger ON bookings_booking;
DROP TRIGGER IF EXISTS pii_fence_email_log_trigger ON integrations_emaillog;
DROP FUNCTION IF EXISTS pii_fence_hardware_request();
DROP FUNCTION IF EXISTS pii_fence_print_request();
DROP FUNCTION IF EXISTS pii_fence_manual_print_log();
DROP FUNCTION IF EXISTS pii_fence_event_registration();
DROP FUNCTION IF EXISTS pii_fence_booking();
DROP FUNCTION IF EXISTS pii_fence_email_log();
DROP FUNCTION IF EXISTS pii_assert_mapped_write_allowed(bigint);
"""


def seed_fences(apps, schema_editor):
    Global = apps.get_model("encryption", "PiiGlobalWriteFence")
    Tenant = apps.get_model("encryption", "PiiMakerspaceWriteFence")
    Makerspace = apps.get_model("makerspaces", "Makerspace")
    Global.objects.get_or_create(pk=1)
    Tenant.objects.bulk_create(
        [Tenant(makerspace_id=pk) for pk in Makerspace.objects.exclude(
            id__in=Tenant.objects.values("makerspace_id")
        ).values_list("id", flat=True)]
    )


def unseed_fences(apps, schema_editor):
    apps.get_model("encryption", "PiiMakerspaceWriteFence").objects.all().delete()
    apps.get_model("encryption", "PiiGlobalWriteFence").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("encryption", "0003_pii_blind_index"),
        ("hardware_requests", "0023_scoped_pii_text_fields"),
        ("printing", "0020_scoped_pii_text_fields"),
        ("events", "0005_event_registration_email_hash"),
        ("bookings", "0005_scoped_pii_text_fields"),
        ("integrations", "0012_scoped_pii_email_log_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="PiiGlobalWriteFence",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("state", models.CharField(choices=[("open", "Open"), ("closed", "Closed")], default="open", max_length=8)),
                ("operation_id", models.UUIDField(blank=True, null=True)),
                ("operation_kind", models.CharField(blank=True, choices=[("enable_transition", "Enable transition"), ("decrypt_rollback", "Decrypt rollback"), ("search_rotation", "Search rotation")], max_length=20, null=True)),
                ("actor_id", models.BigIntegerField(blank=True, null=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("opened_at", models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.AddConstraint(model_name="piiglobalwritefence", constraint=models.CheckConstraint(condition=Q(("pk", 1)), name="ck_pii_global_fence_singleton")),
        migrations.CreateModel(
            name="PiiMakerspaceWriteFence",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("state", models.CharField(choices=[("open", "Open"), ("closed", "Closed")], default="open", max_length=8)),
                ("operation_id", models.UUIDField(blank=True, null=True)),
                ("operation_kind", models.CharField(blank=True, choices=[("enable_transition", "Enable transition"), ("decrypt_rollback", "Decrypt rollback"), ("search_rotation", "Search rotation")], max_length=20, null=True)),
                ("actor_id", models.BigIntegerField(blank=True, null=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("opened_at", models.DateTimeField(blank=True, null=True)),
                ("makerspace", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="pii_write_fence", to="makerspaces.makerspace")),
            ],
        ),
        migrations.RunPython(seed_fences, unseed_fences),
        migrations.RunSQL(FENCE_SQL, REVERSE_FENCE_SQL),
    ]
