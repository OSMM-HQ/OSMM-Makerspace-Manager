# Generated manually for QR print batch de-duplication.

from django.db import migrations, models
from django.db.models import Count


def dedupe_qr_print_batch_items(apps, schema_editor):
    QrPrintBatchItem = apps.get_model("operations", "QrPrintBatchItem")
    duplicates = (
        QrPrintBatchItem.objects.values("batch_id", "qr_code_id")
        .annotate(row_count=Count("id"))
        .filter(row_count__gt=1)
    )
    for duplicate in duplicates:
        items = list(
            QrPrintBatchItem.objects.filter(
                batch_id=duplicate["batch_id"],
                qr_code_id=duplicate["qr_code_id"],
            ).order_by("sort_order", "id")
        )
        keep = items[0]
        newest = items[-1]
        keep.label_text = newest.label_text
        keep.target_type = newest.target_type
        keep.target_id = newest.target_id
        keep.sort_order = newest.sort_order
        keep.save(update_fields=["label_text", "target_type", "target_id", "sort_order"])
        QrPrintBatchItem.objects.filter(id__in=[item.id for item in items[1:]]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0004_stocktake_line_integrity"),
    ]

    operations = [
        migrations.RunPython(dedupe_qr_print_batch_items, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="qrprintbatchitem",
            constraint=models.UniqueConstraint(
                fields=["batch", "qr_code"],
                name="uniq_qr_print_batch_item_qr",
            ),
        ),
    ]
