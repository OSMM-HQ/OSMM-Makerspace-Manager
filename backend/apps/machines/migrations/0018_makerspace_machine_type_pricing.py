from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def _amount(value):
    try:
        value = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return value if value.is_finite() and value >= 0 else None


def migrate_legacy_pricing(apps, schema_editor):
    MachineType = apps.get_model("machines", "MachineType")
    Machine = apps.get_model("machines", "Machine")
    ServiceQueue = apps.get_model("machines", "ServiceQueue")
    Pricing = apps.get_model("machines", "MakerspaceMachineTypePricing")
    pricing_keys = {"rate_per_unit", "flat_fee", "currency", "payment_enabled", "payment_authorized", "authorization"}
    for machine_type in MachineType.objects.all().iterator():
        config = machine_type.capability_config or {}
        if not isinstance(config, dict) or not (set(config) & pricing_keys):
            continue
        rate, fee = _amount(config.get("rate_per_unit")), _amount(config.get("flat_fee"))
        currency = config.get("currency")
        enabled = rate is not None and fee is not None and isinstance(currency, str) and len(currency) == 3 and currency.isalpha()
        space_ids = set(Machine.objects.filter(machine_type_id=machine_type.pk).values_list("makerspace_id", flat=True))
        space_ids |= set(ServiceQueue.objects.filter(machine_type_id=machine_type.pk).values_list("makerspace_id", flat=True))
        if machine_type.makerspace_id:
            space_ids.add(machine_type.makerspace_id)
        for makerspace_id in space_ids:
            Pricing.objects.get_or_create(
                makerspace_id=makerspace_id, machine_type_id=machine_type.pk,
                defaults={"rate_per_unit": rate or Decimal("0"), "flat_fee": fee or Decimal("0"), "payment_enabled": enabled},
            )
        MachineType.objects.filter(pk=machine_type.pk).update(capability_config={key: value for key, value in config.items() if key not in pricing_keys})


class Migration(migrations.Migration):
    dependencies = [("machines", "0017_seed_machine_type_metering_packs"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="MakerspaceMachineTypePricing",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rate_per_unit", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("flat_fee", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("payment_enabled", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("machine_type", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="makerspace_pricing", to="machines.machinetype")),
                ("makerspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="machine_type_pricing", to="makerspaces.makerspace")),
            ],
        ),
        migrations.AddConstraint(model_name="makerspacemachinetypepricing", constraint=models.UniqueConstraint(fields=("makerspace", "machine_type"), name="uniq_makerspace_machine_type_pricing")),
        migrations.AddConstraint(model_name="makerspacemachinetypepricing", constraint=models.CheckConstraint(condition=models.Q(("rate_per_unit__gte", 0)), name="machine_type_pricing_rate_nonnegative")),
        migrations.AddConstraint(model_name="makerspacemachinetypepricing", constraint=models.CheckConstraint(condition=models.Q(("flat_fee__gte", 0)), name="machine_type_pricing_flat_nonnegative")),
        migrations.RunPython(migrate_legacy_pricing, migrations.RunPython.noop),
    ]
