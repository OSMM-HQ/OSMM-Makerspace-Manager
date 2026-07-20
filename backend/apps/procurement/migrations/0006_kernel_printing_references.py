from django.db import migrations, models
import django.db.models.deletion


def copy_legacy_references(apps, schema_editor):
    ToBuyItem = apps.get_model("procurement", "ToBuyItem")
    Machine = apps.get_model("machines", "Machine")
    Pool = apps.get_model("machines", "MachineConsumablePool")

    for item in ToBuyItem.objects.exclude(resulting_printer_id=None).iterator():
        machine = Machine.objects.filter(linked_print_printer_id=item.resulting_printer_id).first()
        machine = machine or Machine.objects.filter(
            legacy_print_printer_id=item.resulting_printer_id
        ).first()
        if machine is None or machine.makerspace_id != item.makerspace_id:
            raise RuntimeError(
                f"ToBuyItem {item.pk} printer {item.resulting_printer_id} has no kernel Machine"
            )
        item.resulting_machine_id = machine.pk
        item.save(update_fields=["resulting_machine"])

    for legacy_field, kernel_field in (
        ("resulting_spool_id", "resulting_pool_id"),
        ("source_spool_id", "source_pool_id"),
    ):
        for item in ToBuyItem.objects.exclude(**{legacy_field: None}).iterator():
            pool = Pool.objects.filter(**{ "legacy_filament_spool_id": getattr(item, legacy_field) }).first()
            if pool is None or pool.makerspace_id != item.makerspace_id:
                raise RuntimeError(
                    f"ToBuyItem {item.pk} spool {getattr(item, legacy_field)} has no kernel MachineConsumablePool"
                )
            setattr(item, kernel_field, pool.pk)
            item.save(update_fields=[kernel_field.removesuffix("_id")])


def reverse_copy_legacy_references(apps, schema_editor):
    # The forward migration is intentionally lossy only with respect to schema,
    # never data. Historical printing tables remain in place, so reversal needs
    # no synthetic legacy rows.
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("procurement", "0005_tobuyitem_source_spool"),
        ("machines", "0014_preservable_historical_ledger_timestamps"),
    ]

    operations = [
        migrations.AddField(
            model_name="tobuyitem",
            name="resulting_machine",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="machines.machine"),
        ),
        migrations.AddField(
            model_name="tobuyitem",
            name="resulting_pool",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="machines.machineconsumablepool"),
        ),
        migrations.AddField(
            model_name="tobuyitem",
            name="source_pool",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="low_stock_to_buy_items", to="machines.machineconsumablepool"),
        ),
        migrations.RunPython(copy_legacy_references, reverse_copy_legacy_references),
        migrations.RemoveField(model_name="tobuyitem", name="resulting_printer"),
        migrations.RemoveField(model_name="tobuyitem", name="resulting_spool"),
        migrations.RemoveField(model_name="tobuyitem", name="source_spool"),
    ]
