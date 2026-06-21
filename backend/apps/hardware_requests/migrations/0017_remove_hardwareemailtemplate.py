from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("hardware_requests", "0016_publictoolloan_return_evidence_notes"),
        ("integrations", "0003_migrate_hardware_email_templates"),
    ]

    operations = [
        migrations.DeleteModel(
            name="HardwareEmailTemplate",
        ),
    ]
