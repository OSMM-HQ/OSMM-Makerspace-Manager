"""Single source of truth for role permissions + makerspace scoping (PRD §4)."""
from apps.accounts.models import User
from apps.makerspaces.models import MakerspaceMembership

ALL = object()  # sentinel: unrestricted (superadmin)


def resolve_scope(actor):
    """Return the set of makerspace ids the actor may act in, or ALL."""
    if actor is None or not getattr(actor, "is_authenticated", False):
        return set()
    if actor.is_superuser or actor.role == User.Role.SUPERADMIN:
        return _superadmin_visible_ids(actor, None)
    scope = set(actor.makerspace_memberships.values_list("makerspace_id", flat=True))
    return _exclude_archived_ids(scope)


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
    ISSUE_DIRECT_LOAN = "issue_direct_loan"  # create a handout with NO reviewed request
    RETURN_REQUEST = "return_request"
    UPLOAD_EVIDENCE = "upload_evidence"
    MANAGE_QR = "manage_qr"
    MANAGE_PRINTING = "manage_printing"
    MANAGE_MACHINES = "manage_machines"
    VIEW_AUDIT = "view_audit"
    TRANSFER_STOCK = "transfer_stock"        # superadmin only
    MANAGE_STAFF = "manage_staff"            # superadmin only
    MANAGE_MAKERSPACE = "manage_makerspace"  # superadmin only


_SPACE_MANAGER_ACTIONS = {
    Action.VIEW_INVENTORY, Action.EDIT_INVENTORY, Action.ACCEPT_REQUEST,
    Action.REJECT_REQUEST, Action.ASSIGN_BOX, Action.ISSUE_REQUEST,
    Action.ISSUE_DIRECT_LOAN, Action.RETURN_REQUEST, Action.UPLOAD_EVIDENCE,
    Action.MANAGE_QR, Action.MANAGE_PRINTING, Action.VIEW_AUDIT,
    Action.MANAGE_MAKERSPACE, Action.MANAGE_MACHINES,
}
# Guest admins are handout-only: accepted request handovers, direct handout, returns,
# and evidence upload. They still cannot review requests or edit inventory setup.
_GUEST_ADMIN_ACTIONS = {
    Action.VIEW_INVENTORY, Action.ASSIGN_BOX, Action.ISSUE_REQUEST,
    Action.ISSUE_DIRECT_LOAN, Action.RETURN_REQUEST, Action.UPLOAD_EVIDENCE,
}
_PRINT_MANAGER_ACTIONS = {
    Action.MANAGE_PRINTING,
}
_INVENTORY_MANAGER_ACTIONS = {
    Action.VIEW_INVENTORY, Action.EDIT_INVENTORY, Action.ACCEPT_REQUEST,
    Action.REJECT_REQUEST, Action.ASSIGN_BOX, Action.ISSUE_REQUEST,
    Action.ISSUE_DIRECT_LOAN, Action.RETURN_REQUEST, Action.UPLOAD_EVIDENCE,
    Action.MANAGE_QR, Action.VIEW_AUDIT,
}
# Authority for non-superadmins is keyed on the PER-MAKERSPACE membership role,
# NOT the global User.role (review fix #3). A user who is globally `space_manager` but only a
# guest_admin member of makerspace B gets only guest_admin actions in B.
_MEMBERSHIP_ROLE_ACTIONS = {
    MakerspaceMembership.Role.SPACE_MANAGER: _SPACE_MANAGER_ACTIONS,
    MakerspaceMembership.Role.GUEST_ADMIN: _GUEST_ADMIN_ACTIONS,
    MakerspaceMembership.Role.INVENTORY_MANAGER: _INVENTORY_MANAGER_ACTIONS,
    MakerspaceMembership.Role.PRINT_MANAGER: _PRINT_MANAGER_ACTIONS,
}


def makerspaces_for_action(actor, action):
    """Return makerspace ids where actor's membership role grants action, or ALL."""
    if actor is None or not getattr(actor, "is_authenticated", False):
        return set()
    if actor.is_superuser or actor.role == User.Role.SUPERADMIN:
        return _superadmin_visible_ids(actor, action)
    roles = [
        role
        for role, actions in _MEMBERSHIP_ROLE_ACTIONS.items()
        if action in actions
    ]
    if not roles:
        return set()
    scope = set(
        actor.makerspace_memberships.filter(role__in=roles).values_list(
            "makerspace_id", flat=True
        )
    )
    return _exclude_archived_ids(scope)


def makerspaces_for_actions(actor, *actions):
    """Union of makerspace scopes across several actions, or ALL.

    A makerspace is included if the actor's membership role grants ANY of the
    given actions there. Used where one console surface is reachable by more
    than one role (e.g. the staff makerspace switcher: VIEW_INVENTORY staff OR
    print managers with only MANAGE_PRINTING)."""
    combined = set()
    for action in actions:
        scope = makerspaces_for_action(actor, action)
        if scope is ALL:
            return ALL
        combined |= scope
    return combined


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
    if makerspace_id is not None and _id_in(makerspace_id, archived_makerspace_ids()):
        return False
    if actor.is_superuser or actor.role == User.Role.SUPERADMIN:
        if makerspace_id is None:
            return True
        if _id_in(makerspace_id, superadmin_hidden_makerspace_ids()):
            # Hard hide: global superpower is withheld for a hidden makerspace.
            # A superadmin who is an explicit member still gets that role's actions.
            role = membership_role(actor, makerspace_id)
            if role is None:
                return False
            return action in _MEMBERSHIP_ROLE_ACTIONS.get(role, set())
        return True
    if makerspace_id is None:
        return False
    role = membership_role(actor, makerspace_id)
    if role is None:
        return False
    return action in _MEMBERSHIP_ROLE_ACTIONS.get(role, set())


def superadmin_hidden_makerspace_ids():
    from apps.makerspaces.models import Makerspace

    return set(
        Makerspace.objects.filter(
            superadmin_access_enabled=False,
        )
        .values_list("id", flat=True)
    )


def archived_makerspace_ids():
    from apps.makerspaces.models import Makerspace

    return set(
        Makerspace.objects.filter(archived_at__isnull=False).values_list(
            "id",
            flat=True,
        )
    )


def _exclude_archived_ids(scope):
    archived = archived_makerspace_ids()
    return scope - archived if archived else scope


def _id_in(makerspace_id, ids):
    if makerspace_id in ids:
        return True
    try:
        return int(makerspace_id) in ids
    except (TypeError, ValueError):
        return False


def _is_superadmin(actor):
    return bool(
        actor is not None
        and getattr(actor, "is_authenticated", False)
        and (actor.is_superuser or actor.role == User.Role.SUPERADMIN)
    )


def _superadmin_hidden_to_exclude(actor, action=None):
    """Hidden makerspace ids a GLOBAL superadmin must be cut off from.

    A makerspace with superadmin_access_enabled=False is excluded UNLESS the
    superadmin holds an explicit MakerspaceMembership there (granting `action`,
    when given) — a superadmin who is also a real member keeps that membership's
    role-scoped access, but never global superpower (review fix #2)."""
    hidden = superadmin_hidden_makerspace_ids()
    if not hidden:
        return set()
    memberships = actor.makerspace_memberships.filter(makerspace_id__in=hidden)
    if action is None:
        member_ok = set(memberships.values_list("makerspace_id", flat=True))
    else:
        granting = [r for r, acts in _MEMBERSHIP_ROLE_ACTIONS.items() if action in acts]
        member_ok = (
            set(
                memberships.filter(role__in=granting).values_list(
                    "makerspace_id", flat=True
                )
            )
            if granting
            else set()
        )
    return hidden - member_ok


def _superadmin_visible_ids(actor, action=None):
    """Concrete id set a global superadmin may act in (all makerspaces minus the
    hard-hidden, non-member ones and archived ones). Returns ALL when there is
    no exclusion so the fast path is preserved for the common case."""
    excluded = _superadmin_hidden_to_exclude(actor, action) | archived_makerspace_ids()
    if not excluded:
        return ALL
    from apps.makerspaces.models import Makerspace

    return set(Makerspace.objects.exclude(id__in=excluded).values_list("id", flat=True))


def superadmin_hidden_block_applies(actor, makerspace_id, action=None):
    """True when a global superadmin must be HARD-blocked from `makerspace_id`."""
    if not _is_superadmin(actor) or makerspace_id is None:
        return False
    if not _id_in(makerspace_id, superadmin_hidden_makerspace_ids()):
        return False
    role = membership_role(actor, makerspace_id)
    if role is None:
        return True  # no membership -> global superpower is withheld
    if action is None:
        return False  # legitimate member: membership role governs, not blocked
    return action not in _MEMBERSHIP_ROLE_ACTIONS.get(role, set())


def hide_from_superadmin(actor, queryset, field="makerspace_id"):
    """Exclude hard-hidden makerspaces for a global superadmin. Delegates to the
    same policy as the RBAC scopes so a superadmin who is an explicit member of a
    hidden space is NOT excluded (no contradiction with scope_by_action)."""
    if not _is_superadmin(actor):
        return queryset
    excluded = _superadmin_hidden_to_exclude(actor, None)
    if not excluded:
        return queryset
    return queryset.exclude(**{f"{field}__in": excluded})
