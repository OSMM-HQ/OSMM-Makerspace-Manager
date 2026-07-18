from django.db import migrations, models
from django.db.models import Q
from django.db.models.functions import Lower


def check_no_duplicate_emails(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    duplicates = list(
        User.objects.exclude(email="")
        .annotate(normalized_email=Lower("email"))
        .values("normalized_email")
        .annotate(total=models.Count("id"))
        .filter(total__gt=1)
        .values_list("normalized_email", flat=True)
    )
    if duplicates:
        joined = ", ".join(sorted(duplicates))
        raise RuntimeError(
            "Cannot add case-insensitive email uniqueness: duplicate emails found "
            f"({joined}). Deduplicate them before applying this migration."
        )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_user_must_change_password")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="display_name",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="user",
            name="email_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="DailyOtpEmailCounter",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("day", models.DateField(unique=True)),
                ("count", models.PositiveIntegerField(default=0)),
            ],
        ),
        migrations.CreateModel(
            name="EmailVerificationChallenge",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.CharField(max_length=254)),
                ("code_digest", models.CharField(max_length=128)),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("failed_attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="email_challenges", to="accounts.user")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["user", "email", "expires_at"], name="accounts_em_user_id_fcb5b0_idx"),
                    models.Index(condition=Q(("consumed_at__isnull", True)), fields=["user", "email"], name="email_challenge_active_idx"),
                ],
            },
        ),
        migrations.RunPython(check_no_duplicate_emails, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                Lower("email"), condition=~Q(email=""), name="uniq_ci_nonempty_email"
            ),
        ),
    ]
