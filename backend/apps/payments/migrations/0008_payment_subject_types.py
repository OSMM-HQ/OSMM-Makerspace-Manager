from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("payments", "0007_connect_account_assignment_generation")]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="subject_type",
            field=models.CharField(
                choices=[
                    ("machine_service_request", "Machine service request"),
                    ("booking", "Booking"),
                    ("event_registration", "Event registration"),
                    ("makerspace_membership", "Makerspace membership"),
                ],
                max_length=48,
            ),
        ),
    ]
