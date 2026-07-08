from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hardware_requests", "0021_alter_returnevent_box_publicproblemreport"),
    ]

    operations = [
        migrations.AddField(
            model_name="publicproblemreport",
            name="outcome",
            field=models.CharField(
                blank=True,
                choices=[
                    ("no_issue", "No Issue"),
                    ("damaged", "Damaged"),
                    ("missing", "Missing"),
                    ("needs_fix", "Needs Fix"),
                ],
                db_index=True,
                default="",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="publicproblemreport",
            name="triage_note",
            field=models.TextField(blank=True, default=""),
        ),
    ]