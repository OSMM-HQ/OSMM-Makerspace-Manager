import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


TRIGGER_SQL = """
CREATE FUNCTION encryption_prevent_key_delete() RETURNS trigger AS $$
BEGIN
    -- Key rows are never deletable through ordinary ORM/admin/SQL paths. The sole
    -- exception is the superadmin makerspace-purge break-glass, which sets the
    -- transaction-scoped GUC app.allow_immutable_delete='on' (managed Postgres) or
    -- runs under session_replication_role='replica' (self-host, which disables this
    -- trigger entirely). This mirrors the audit/evidence purge-aware immutability
    -- pattern so a purged makerspace's PROTECT FK cannot block teardown.
    IF current_setting('app.allow_immutable_delete', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'Encryption key rows cannot be deleted';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER encryption_prevent_key_delete_trigger
BEFORE DELETE ON encryption_makerspaceencryptionkey
FOR EACH ROW EXECUTE FUNCTION encryption_prevent_key_delete();
"""

REVERSE_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS encryption_prevent_key_delete_trigger
ON encryption_makerspaceencryptionkey;
DROP FUNCTION IF EXISTS encryption_prevent_key_delete();
"""


class Migration(migrations.Migration):
    initial = True

    dependencies = [("makerspaces", "0039_seed_and_backfill_roles")]

    operations = [
        migrations.CreateModel(
            name="MakerspaceEncryptionKey",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("version", models.PositiveIntegerField()),
                ("wrapped_dek", models.BinaryField()),
                (
                    "broker_backend",
                    models.CharField(
                        choices=[("local", "Local master key"), ("aws_kms", "AWS KMS")],
                        max_length=16,
                    ),
                ),
                ("broker_key_id", models.CharField(max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("rotated", "Rotated"),
                            ("disabled", "Disabled"),
                        ],
                        default="active",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("rotated_at", models.DateTimeField(blank=True, null=True)),
                ("disabled_at", models.DateTimeField(blank=True, null=True)),
                (
                    "makerspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="encryption_keys",
                        to="makerspaces.makerspace",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="makerspaceencryptionkey",
            constraint=models.UniqueConstraint(
                fields=("makerspace", "version"), name="uniq_makerspace_dek_version"
            ),
        ),
        migrations.AddConstraint(
            model_name="makerspaceencryptionkey",
            constraint=models.CheckConstraint(
                condition=Q(("version__gte", 1)),
                name="ck_makerspace_dek_version_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="makerspaceencryptionkey",
            constraint=models.UniqueConstraint(
                condition=Q(("status", "active")),
                fields=("makerspace",),
                name="uniq_makerspace_active_dek",
            ),
        ),
        migrations.AddIndex(
            model_name="makerspaceencryptionkey",
            index=models.Index(fields=["makerspace", "status"], name="encryption__makersp_152d17_idx"),
        ),
        migrations.RunSQL(TRIGGER_SQL, REVERSE_TRIGGER_SQL),
    ]
