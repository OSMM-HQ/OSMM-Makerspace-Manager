import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("events", "0004_scoped_pii_text_fields"), ("encryption", "0002_search_key_generation")]

    operations = [
        migrations.AddField(model_name="eventregistration", name="email_exact_hash", field=models.BinaryField(max_length=32, null=True, editable=False)),
        migrations.AddField(model_name="eventregistration", name="email_hash_generation", field=models.ForeignKey(null=True, editable=False, on_delete=django.db.models.deletion.PROTECT, to="encryption.searchkeygeneration")),
        migrations.AddConstraint(model_name="eventregistration", constraint=models.UniqueConstraint(fields=("event", "email_hash_generation", "email_exact_hash"), condition=Q(("email_exact_hash__isnull", False), ("email_hash_generation__isnull", False)), name="uniq_event_registration_email_hash")),
    ]
