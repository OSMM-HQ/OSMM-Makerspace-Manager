from django.db import migrations


def backfill_box_loan_containers(apps, schema_editor):
    box_model = apps.get_model("boxes", "Box")
    loan_model = apps.get_model("hardware_requests", "PublicToolLoan")
    loans = loan_model.objects.filter(
        status="checked_out",
        target_type="box",
        container__isnull=True,
    )
    for loan in loans.iterator():
        box_exists = box_model.objects.filter(
            pk=loan.target_id,
            makerspace_id=loan.makerspace_id,
        ).exists()
        if not box_exists:
            continue
        has_conflict = loan_model.objects.filter(
            status="checked_out",
            container_id=loan.target_id,
        ).exclude(pk=loan.pk).exists()
        if has_conflict:
            continue
        loan.container_id = loan.target_id
        loan.save(update_fields=["container"])


class Migration(migrations.Migration):
    dependencies = [
        ("boxes", "0001_initial"),
        ("hardware_requests", "0018_hardwarerequest_requester_name"),
    ]

    operations = [
        migrations.RunPython(backfill_box_loan_containers, migrations.RunPython.noop),
    ]
