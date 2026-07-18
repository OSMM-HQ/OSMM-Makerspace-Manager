from django.conf import settings
from django.db import migrations, models


def migrate_print_status_lookup_policy(apps, schema_editor):
    Makerspace = apps.get_model("makerspaces", "Makerspace")
    Makerspace.objects.filter(
        public_print_status_lookup_policy__in=["checkin_verified", "email_unverified"]
    ).update(public_print_status_lookup_policy="token_only")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_member_registration_and_email_verification"),
        ("printing", "0020_scoped_pii_text_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="printrequestfile",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="printrequestfile",
            name="owner_checkin_user_id",
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
        ),
        migrations.AddIndex(
            model_name="printrequestfile",
            index=models.Index(fields=["owner", "attached_at"], name="printing_pr_owner_i_cb8db0_idx"),
        ),
        migrations.RunPython(migrate_print_status_lookup_policy, migrations.RunPython.noop),
    ]
