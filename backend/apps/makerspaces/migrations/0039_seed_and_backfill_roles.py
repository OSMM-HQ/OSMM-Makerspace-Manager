from django.db import migrations


DEFAULT_ROLE_DEFINITIONS = (
    ("space_manager", "Space Manager", ["accept_request", "assign_box", "edit_inventory", "issue_direct_loan", "issue_request", "manage_bookings", "manage_events", "manage_machines", "manage_makerspace", "manage_printing", "manage_qr", "reject_request", "return_request", "upload_evidence", "view_audit", "view_inventory"]),
    ("guest_admin", "Guest Admin", ["assign_box", "issue_direct_loan", "issue_request", "return_request", "upload_evidence", "view_inventory"]),
    ("inventory_manager", "Inventory Manager", ["accept_request", "assign_box", "edit_inventory", "issue_direct_loan", "issue_request", "manage_qr", "reject_request", "return_request", "upload_evidence", "view_audit", "view_inventory"]),
    ("print_manager", "Print Manager", ["manage_printing"]),
    ("machine_manager", "Machine Manager", ["manage_machines"]),
)


def forwards(apps, schema_editor):
    MakerspaceRole = apps.get_model("makerspaces", "MakerspaceRole")
    Makerspace = apps.get_model("makerspaces", "Makerspace")
    MakerspaceMembership = apps.get_model("makerspaces", "MakerspaceMembership")

    legacy_roles = {}
    for makerspace in Makerspace.objects.all().iterator():
        role_ids = {}
        for legacy_role, display_name, granted_actions in DEFAULT_ROLE_DEFINITIONS:
            role, _ = MakerspaceRole.objects.update_or_create(
                makerspace_id=makerspace.id,
                legacy_role=legacy_role,
                defaults={
                    "name": display_name,
                    "slug": legacy_role,
                    "granted_actions": sorted(granted_actions),
                    "is_default": True,
                    "is_protected": True,
                },
            )
            role_ids[legacy_role] = role.id
        legacy_roles[makerspace.id] = role_ids

    for makerspace_id, role_ids in legacy_roles.items():
        for legacy_role, role_id in role_ids.items():
            MakerspaceMembership.objects.filter(
                makerspace_id=makerspace_id,
                role=legacy_role,
            ).update(assigned_role_id=role_id)


def backwards(apps, schema_editor):
    MakerspaceRole = apps.get_model("makerspaces", "MakerspaceRole")
    MakerspaceMembership = apps.get_model("makerspaces", "MakerspaceMembership")

    MakerspaceMembership.objects.filter(
        assigned_role__is_default=True,
    ).update(assigned_role_id=None)
    MakerspaceRole.objects.filter(is_default=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("makerspaces", "0038_makerspace_roles"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
