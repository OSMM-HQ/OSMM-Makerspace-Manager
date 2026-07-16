from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("makerspaces", "0034_enable_maintenance_module")]

    operations = [
        migrations.AlterField(
            model_name="makerspacemembership",
            name="role",
            field=models.CharField(
                choices=[
                    ("space_manager", "Space Manager"),
                    ("guest_admin", "Guest Admin"),
                    ("inventory_manager", "Inventory Manager"),
                    ("print_manager", "Print Manager"),
                    ("machine_manager", "Machine Manager"),
                ],
                default="space_manager",
                max_length=32,
            ),
        ),
    ]
