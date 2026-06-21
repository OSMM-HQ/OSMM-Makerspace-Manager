from django.db import migrations


def forwards(apps, schema_editor):
    Old = apps.get_model("hardware_requests", "HardwareEmailTemplate")
    New = apps.get_model("integrations", "EmailTemplate")

    for old in Old.objects.all():
        New.objects.update_or_create(
            makerspace_id=old.makerspace_id,
            stream="hardware",
            audience="requester",
            key=old.key,
            defaults={
                "subject": old.subject,
                "text_body": old.text_body,
                "html_body": old.html_body,
                "is_active": old.is_active,
            },
        )


def reverse(apps, schema_editor):
    New = apps.get_model("integrations", "EmailTemplate")
    New.objects.filter(stream="hardware", audience="requester").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0002_emailtemplate"),
        ("hardware_requests", "0016_publictoolloan_return_evidence_notes"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse),
    ]
