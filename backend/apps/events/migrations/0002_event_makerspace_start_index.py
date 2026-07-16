from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("events", "0001_initial")]

    operations = [
        migrations.AddIndex(
            model_name="event",
            index=models.Index(fields=["makerspace", "starts_at"], name="event_ms_starts_idx"),
        ),
    ]
