from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("makerspaces", "0016_migrate_tenant_frontend_hosts"),
    ]

    operations = [
        migrations.DeleteModel(
            name="TenantFrontend",
        ),
    ]
