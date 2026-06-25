from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hardware_requests", "0019_backfill_box_loan_containers"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="hardwarerequest",
            index=models.Index(
                fields=["return_due_at", "id"],
                name="hwreq_return_reminder_due_idx",
                condition=models.Q(
                    return_reminder_sent_at__isnull=True,
                    status__in=["issued", "partially_returned"],
                ),
            ),
        ),
    ]