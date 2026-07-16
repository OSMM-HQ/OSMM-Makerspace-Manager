from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0009_rename_integration_emaill_makersp_8c9fd1_idx_integration_makersp_1d5eb0_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="DailyEmailCounter",
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
                ("day", models.DateField()),
                ("count", models.PositiveIntegerField(default=0)),
                (
                    "makerspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="daily_email_counters",
                        to="makerspaces.makerspace",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("makerspace", "day"),
                        name="uniq_daily_email_counter",
                    )
                ],
            },
        ),
    ]
