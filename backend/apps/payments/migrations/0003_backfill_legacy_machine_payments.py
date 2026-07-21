from django.db import migrations


def backfill_legacy_machine_payments(apps, schema_editor):
    MachineServiceRequest = apps.get_model("machines", "MachineServiceRequest")
    MakerspacePaymentSettings = apps.get_model("payments", "MakerspacePaymentSettings")
    Payment = apps.get_model("payments", "Payment")

    currencies = dict(MakerspacePaymentSettings.objects.values_list("makerspace_id", "default_currency"))
    requests = MachineServiceRequest.objects.filter(payment_amount__isnull=False, payment_amount__gt=0)
    for request in requests.iterator():
        if Payment.objects.filter(
            makerspace_id=request.makerspace_id,
            subject_type="machine_service_request",
            subject_id=request.pk,
        ).exists():
            continue
        Payment.objects.create(
            makerspace_id=request.makerspace_id,
            subject_type="machine_service_request",
            subject_id=request.pk,
            member_id=request.member_id,
            amount=request.payment_amount,
            currency=currencies.get(request.makerspace_id, "usd"),
            status="paid_offline" if request.payment_status == "paid" else "pending",
            created_by_id=request.accepted_by_id or request.handled_by_id or request.requester_id,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0002_payment_and_processed_stripe_event"),
        ("machines", "0016_machine_metering_generalization"),
    ]

    operations = [migrations.RunPython(backfill_legacy_machine_payments, migrations.RunPython.noop)]
