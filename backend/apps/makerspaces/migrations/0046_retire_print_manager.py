from django.db import migrations


def migrate_print_manager_memberships(apps, schema_editor):
    Makerspace = apps.get_model("makerspaces", "Makerspace")
    MakerspaceMembership = apps.get_model("makerspaces", "MakerspaceMembership")
    MakerspaceRole = apps.get_model("makerspaces", "MakerspaceRole")

    for makerspace in Makerspace.objects.select_for_update().order_by("id"):
        roles = {
            role.legacy_role: role
            for role in MakerspaceRole.objects.select_for_update().filter(
                makerspace_id=makerspace.id,
                is_default=True,
                is_protected=True,
                legacy_role__in=["print_manager", "machine_manager"],
            )
        }
        print_role = roles.get("print_manager")
        machine_role = roles.get("machine_manager")

        if print_role is not None and machine_role is not None:
            assigned = list(
                MakerspaceMembership.objects.select_for_update().filter(
                    makerspace_id=makerspace.id,
                    assigned_role_id=print_role.id,
                )
            )
            for membership in assigned:
                membership.assigned_role_id = machine_role.id
                membership.role = "machine_manager"
            if assigned:
                MakerspaceMembership.objects.bulk_update(
                    assigned, ["assigned_role", "role"]
                )

        unassigned = list(
            MakerspaceMembership.objects.select_for_update().filter(
                makerspace_id=makerspace.id,
                assigned_role__isnull=True,
                role="print_manager",
            )
        )
        for membership in unassigned:
            membership.role = "machine_manager"
        if unassigned:
            MakerspaceMembership.objects.bulk_update(unassigned, ["role"])


class Migration(migrations.Migration):
    dependencies = [("makerspaces", "0045_membership_join_policy_referrals")]

    operations = [
        migrations.RunPython(migrate_print_manager_memberships, migrations.RunPython.noop),
    ]
