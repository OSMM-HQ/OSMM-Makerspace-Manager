# Generated manually for the audit-fixes Phase 2 stocktake integrity guard.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0003_qrprintbatch_qrbatch_ms_created_idx_and_more"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="stocktakeline",
            constraint=models.UniqueConstraint(
                fields=("stocktake", "product", "condition", "container"),
                condition=models.Q(("product__isnull", False)),
                nulls_distinct=False,
                name="uniq_stocktake_product_bucket_container",
            ),
        ),
        migrations.AddConstraint(
            model_name="stocktakeline",
            constraint=models.UniqueConstraint(
                fields=("stocktake", "asset"),
                condition=models.Q(("asset__isnull", False)),
                name="uniq_stocktake_asset_line",
            ),
        ),
    ]