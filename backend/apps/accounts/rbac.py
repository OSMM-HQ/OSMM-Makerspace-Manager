"""Single source of truth for role permissions + makerspace scoping (PRD §4)."""
from apps.accounts.models import User
from apps.makerspaces.models import MakerspaceMembership

ALL = object()  # sentinel: unrestricted (superadmin)


def resolve_scope(actor):
    """Return the set of makerspace ids the actor may act in, or ALL."""
    if actor is None or not getattr(actor, "is_authenticated", False):
        return set()
    if actor.is_superuser or actor.role == User.Role.SUPERADMIN:
        return ALL
    return set(actor.makerspace_memberships.values_list("makerspace_id", flat=True))


def scope_by_makerspace(actor, queryset, makerspace_field="makerspace_id"):
    """Filter a makerspace-owned queryset to the actor's scope (superadmin: unchanged)."""
    scope = resolve_scope(actor)
    if scope is ALL:
        return queryset
    if not scope:
        return queryset.none()
    return queryset.filter(**{f"{makerspace_field}__in": scope})


class Action:
    VIEW_INVENTORY = "view_inventory"
    EDIT_INVENTORY = "edit_inventory"
    ACCEPT_REQUEST = "accept_request"
    REJECT_REQUEST = "reject_request"
    ASSIGN_BOX = "assign_box"
    ISSUE_REQUEST = "issue_request"
    RETURN_REQUEST = "return_request"
    UPLOAD_EVIDENCE = "upload_evidence"
    MANAGE_QR = "manage_qr"
    MANAGE_PRINTING = "manage_printing"
    TRANSFER_STOCK = "transfer_stock"        # superadmin only
    MANAGE_STAFF = "manage_staff"            # superadmin only
    MANAGE_MAKERSPACE = "manage_makerspace"  # superadmin only


_ADMIN_ACTIONS = {
    Action.VIEW_INVENTORY, Action.EDIT_INVENTORY, Action.ACCEPT_REQUEST,
    Action.REJECT_REQUEST, Action.ASSIGN_BOX, Action.ISSUE_REQUEST,
    Action.RETURN_REQUEST, Action.UPLOAD_EVIDENCE, Action.MANAGE_QR,
    Action.MANAGE_PRINTING,
}
_GUEST_ADMIN_ACTIONS = {
    Action.VIEW_INVENTORY, Action.ASSIGN_BOX, Action.ISSUE_REQUEST,
    Action.UPLOAD_EVIDENCE,
}
_PRINT_MANAGER_ACTIONS = {
    Action.MANAGE_PRINTING,
}
# Authority for non-superadmins is keyed on the PER-MAKERSPACE membership role,
# NOT the global User.role (review fix #3). A user who is globally `admin` but only a
# guest_admin member of makerspace B gets only guest_admin actions in B.
_MEMBERSHIP_ROLE_ACTIONS = {
    MakerspaceMembership.Role.ADMIN: _ADMIN_ACTIONS,
    MakerspaceMembership.Role.GUEST_ADMIN: _GUEST_ADMIN_ACTIONS,
    MakerspaceMembership.Role.PRINT_MANAGER: _PRINT_MANAGER_ACTIONS,
}


def makerspaces_for_action(actor, action):
    """Return makerspace ids where actor's membership role grants action, or ALL."""
    if actor is None or not getattr(actor, "is_authenticated", False):
        return set()
    if actor.is_superuser or actor.role == User.Role.SUPERADMIN:
        return ALL
    roles = [
        role
        for role, actions in _MEMBERSHIP_ROLE_ACTIONS.items()
        if action in actions
    ]
    if not roles:
        return set()
    return set(
        actor.makerspace_memberships.filter(role__in=roles).values_list(
            "makerspace_id", flat=True
        )
    )


def scope_by_action(actor, action, queryset, field="makerspace_id"):
    """Filter queryset to makerspaces where actor's membership grants action."""
    scope = makerspaces_for_action(actor, action)
    if scope is ALL:
        return queryset
    if not scope:
        return queryset.none()
    return queryset.filter(**{f"{field}__in": scope})


def membership_role(actor, makerspace_id):
    """Return the actor's MakerspaceMembership.role for this makerspace, or None."""
    membership = actor.makerspace_memberships.filter(
        makerspace_id=makerspace_id
    ).first()
    return membership.role if membership else None


def can(actor, action, makerspace_id=None):
    """True if `actor` may perform `action` within `makerspace_id`.

    Superadmin: everything. Everyone else: authority is per-makerspace, so a
    makerspace_id is required and the membership role decides the allowed actions."""
    if actor is None or not getattr(actor, "is_authenticated", False):
        return False
    if actor.is_superuser or actor.role == User.Role.SUPERADMIN:
        return True
    if makerspace_id is None:
        return False
    role = membership_role(actor, makerspace_id)
    if role is None:
        return False
    return action in _MEMBERSHIP_ROLE_ACTIONS.get(role, set())
