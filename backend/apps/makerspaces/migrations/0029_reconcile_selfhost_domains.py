from django.conf import settings
from django.db import migrations
from django.utils import timezone


def promote_selfhost_domains(apps, schema_editor):
    if str(settings.PLATFORM_DOMAIN_SUFFIX or "").strip():
        return  # managed instance — leave the TXT-verification flow untouched
    Makerspace = apps.get_model("makerspaces", "Makerspace")
    (
        Makerspace.objects.filter(archived_at__isnull=True, frontend_domain__isnull=False)
        .exclude(frontend_domain="")
        .exclude(frontend_domain_status="verified")
        .update(frontend_domain_status="verified", domain_verified_at=timezone.now())
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("makerspaces", "0028_makerspace_frontend_domain_changed_at"),
    ]

    operations = [
        migrations.RunPython(promote_selfhost_domains, noop),
    ]
