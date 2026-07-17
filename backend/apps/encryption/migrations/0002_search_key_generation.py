from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("encryption", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="SearchKeyGeneration",
            fields=[
                ("generation", models.PositiveIntegerField(primary_key=True, serialize=False)),
                ("key_fingerprint", models.BinaryField(max_length=32, unique=True)),
                ("status", models.CharField(choices=[("building", "Building"), ("active", "Active"), ("retired", "Retired")], max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
                ("retired_at", models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.AddConstraint(model_name="searchkeygeneration", constraint=models.CheckConstraint(condition=Q(("generation__gte", 1)), name="ck_search_generation_positive")),
        migrations.AddConstraint(model_name="searchkeygeneration", constraint=models.UniqueConstraint(condition=Q(("status", "active")), fields=("status",), name="uniq_active_search_generation")),
    ]
