"""Seeded makerspace role presets and runtime initialization helpers."""

DEFAULT_ROLE_DEFINITIONS = (
    ("space_manager", "Space Manager", ["accept_request", "assign_box", "edit_inventory", "issue_direct_loan", "issue_request", "manage_bookings", "manage_events", "manage_machines", "manage_makerspace", "manage_printing", "manage_qr", "reject_request", "return_request", "upload_evidence", "view_audit", "view_inventory"]),
    ("guest_admin", "Guest Admin", ["assign_box", "issue_direct_loan", "issue_request", "return_request", "upload_evidence", "view_inventory"]),
    ("inventory_manager", "Inventory Manager", ["accept_request", "assign_box", "edit_inventory", "issue_direct_loan", "issue_request", "manage_qr", "reject_request", "return_request", "upload_evidence", "view_audit", "view_inventory"]),
    ("print_manager", "Print Manager", ["manage_printing"]),
    ("machine_manager", "Machine Manager", ["manage_machines"]),
)


def ensure_default_roles(makerspace):
    """Create missing protected defaults without overwriting administrator edits."""
    from apps.makerspaces.models import MakerspaceRole

    for legacy_role, display_name, granted_actions in DEFAULT_ROLE_DEFINITIONS:
        MakerspaceRole.objects.get_or_create(
            makerspace=makerspace,
            legacy_role=legacy_role,
            defaults={
                "name": display_name,
                "slug": legacy_role,
                "granted_actions": sorted(granted_actions),
                "is_default": True,
                "is_protected": True,
            },
        )
