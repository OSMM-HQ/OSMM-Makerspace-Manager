import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


FUNCTION_SQL = """
CREATE FUNCTION pii_bloom_contains(candidate bytea, query bytea) RETURNS boolean AS $$
BEGIN
  IF octet_length(candidate) <> 256 OR octet_length(query) <> 256 THEN
    RAISE EXCEPTION 'pii bloom bit arrays must be 256 bytes';
  END IF;
  FOR i IN 0..255 LOOP
    IF (get_byte(candidate, i) & get_byte(query, i)) <> get_byte(query, i) THEN RETURN false; END IF;
  END LOOP;
  RETURN true;
END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
"""


class Migration(migrations.Migration):
    dependencies = [("encryption", "0002_search_key_generation"), ("hardware_requests", "0023_scoped_pii_text_fields"), ("printing", "0020_scoped_pii_text_fields"), ("events", "0005_event_registration_email_hash"), ("bookings", "0005_scoped_pii_text_fields"), ("integrations", "0012_scoped_pii_email_log_fields")]

    operations = [
        migrations.CreateModel(name="PiiBlindIndex", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("model_label", models.CharField(max_length=96)), ("object_id", models.BigIntegerField()),
            ("field_name", models.CharField(max_length=64)), ("bloom_bits", models.BinaryField(max_length=256)),
            ("exact_hash", models.BinaryField(blank=True, max_length=32, null=True)),
            ("algorithm_version", models.PositiveSmallIntegerField(default=1)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("makerspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="makerspaces.makerspace")),
            ("search_generation", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="encryption.searchkeygeneration")),
        ]),
        migrations.AddConstraint(model_name="piiblindindex", constraint=models.UniqueConstraint(fields=("makerspace", "model_label", "object_id", "field_name"), name="uniq_pii_blind_index_source_field")),
        migrations.AddConstraint(model_name="piiblindindex", constraint=models.CheckConstraint(condition=Q(("algorithm_version", 1)), name="ck_pii_blind_index_algorithm_v1")),
        migrations.AddIndex(model_name="piiblindindex", index=models.Index(fields=["makerspace", "model_label", "field_name"], name="encryption__makersp_9d5c77_idx")),
        migrations.AddIndex(model_name="piiblindindex", index=models.Index(fields=["search_generation", "makerspace", "model_label", "field_name", "exact_hash"], name="pii_bi_generation_exact_idx")),
        migrations.RunSQL(FUNCTION_SQL, "DROP FUNCTION IF EXISTS pii_bloom_contains(bytea, bytea);"),
    ]
