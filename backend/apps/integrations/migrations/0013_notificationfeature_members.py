from django.db import migrations, models


FEATURE_CHOICES = [
    ("hardware_requests", "Hardware requests"),
    ("printing", "Printing"),
    ("events", "Events"),
    ("bookings", "Bookings"),
    ("maintenance", "Maintenance"),
    ("members", "Members"),
]


class Migration(migrations.Migration):
    dependencies = [("integrations", "0012_scoped_pii_email_log_fields")]

    operations = [
        migrations.AlterField(
            model_name="notificationpreference",
            name="feature",
            field=models.CharField(choices=FEATURE_CHOICES, max_length=32),
        ),
        migrations.AlterField(
            model_name="notificationdeliverylog",
            name="feature",
            field=models.CharField(choices=FEATURE_CHOICES, max_length=32),
        ),
    ]
