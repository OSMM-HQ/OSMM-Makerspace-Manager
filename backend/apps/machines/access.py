"""Object-level authorization for the Machines module.

Builds on apps.accounts.rbac (which already enforces hard-hide + archived scoping).
Three tiers:
  1. MANAGE_MACHINES (Space Manager + Superadmin) — full control of every machine.
  2. Type managers — hold a machine type's managing_action (3d_printer -> manage_printing).
  3. Per-machine operators (MachineOperator.access_level: operate/manage/full).

Every operator check re-verifies LIVE active membership, so a stale assignment row for a
removed/suspended member is inert and can never become a cross-tenant or stale escalation.
"""
from apps.accounts import rbac
from apps.accounts.models import User
from apps.accounts.rbac import Action

from .models import Machine, MachineOperator, MachineType

FULL = MachineOperator.AccessLevel.FULL
MANAGE = MachineOperator.AccessLevel.MANAGE
OPERATE = MachineOperator.AccessLevel.OPERATE


def is_active_member(user, makerspace_id):
    """True if `user` is a live, active member of the makerspace (not merely a stored row)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "access_status", None) != User.AccessStatus.ACTIVE:
        return False
    if not getattr(user, "is_active", False):
        return False
    return user.makerspace_memberships.filter(makerspace_id=makerspace_id).exists()


def operator_level(actor, machine):
    """The actor's access level on this machine, or None. Inert without live membership."""
    if not is_active_member(actor, machine.makerspace_id):
        return None
    row = MachineOperator.objects.filter(machine=machine, user=actor).first()
    return row.access_level if row else None


def _type_manager(actor, makerspace_id, machine_type):
    action = (getattr(machine_type, "managing_action", "") or "").strip()
    return bool(action) and rbac.can(actor, action, makerspace_id)


def is_machine_admin(actor, machine):
    """Tier 1/2: MANAGE_MACHINES or the machine type's manager (e.g. Print Manager)."""
    return can_create_machine(actor, machine.makerspace_id, machine.machine_type)


def is_full_operator(actor, machine):
    return operator_level(actor, machine) == FULL


# --- Roster (create) ---------------------------------------------------------

def can_create_machine(actor, makerspace_id, machine_type):
    if rbac.can(actor, Action.MANAGE_MACHINES, makerspace_id):
        return True
    return _type_manager(actor, makerspace_id, machine_type)


# --- Per-machine operate / manage --------------------------------------------

def can_operate_machine(actor, machine):
    """Set status, log usage, log errors."""
    return can_manage_machine(actor, machine) or operator_level(actor, machine) is not None


def can_manage_machine(actor, machine):
    """Edit machine fields + upload/delete documents."""
    if is_machine_admin(actor, machine):
        return True
    return operator_level(actor, machine) in {MANAGE, FULL}


# --- Lifecycle ---------------------------------------------------------------

def can_retire_machine(actor, machine):
    """Retire (is_active=False): admin/type-manager OR a full operator."""
    return is_machine_admin(actor, machine) or is_full_operator(actor, machine)


def can_unretire_machine(actor, machine):
    """Reactivate: admin/type-manager ONLY (a machine's operators cannot self-resurrect it)."""
    return is_machine_admin(actor, machine)


# --- Operator delegation -----------------------------------------------------

def can_delegate_operators(actor, machine):
    '''View/delegate the operator roster: admin/type-manager or a full operator.'''
    return is_machine_admin(actor, machine) or is_full_operator(actor, machine)


_CAPABILITY_KEYS = (
    "can_operate", "can_edit", "can_delegate", "can_retire", "can_unretire",
)


def machine_capabilities(actor, machine):
    '''Return the server-derived actions available to the actor for this machine.'''
    return {
        'can_operate': can_operate_machine(actor, machine),
        'can_edit': can_manage_machine(actor, machine),
        'can_delegate': can_delegate_operators(actor, machine),
        'can_retire': can_retire_machine(actor, machine),
        'can_unretire': can_unretire_machine(actor, machine),
    }


def capabilities_for_machines(actor, machines):
    """Bulk per-machine capabilities in O(1) queries regardless of fleet size.

    Memoizes the makerspace-level rbac decisions (MANAGE_MACHINES + each type's
    managing_action + live membership are constant across machines in the same
    makerspace) and fetches every operator level in a single query, so a list
    endpoint never re-derives capabilities per row. Requires the machines to have
    `machine_type` loaded (the list view select_relates it) so no extra type query
    fires. Falls back to False for an anonymous actor.
    """
    machines = list(machines)
    empty = {key: False for key in _CAPABILITY_KEYS}
    if actor is None or not getattr(actor, "is_authenticated", False):
        return {m.pk: dict(empty) for m in machines}

    op_levels = dict(
        MachineOperator.objects.filter(machine__in=machines, user=actor)
        .values_list("machine_id", "access_level")
    )
    manage_cache, type_cache, member_cache = {}, {}, {}

    def _manage(ms_id):
        if ms_id not in manage_cache:
            manage_cache[ms_id] = rbac.can(actor, Action.MANAGE_MACHINES, ms_id)
        return manage_cache[ms_id]

    def _type_mgr(ms_id, action):
        action = (action or "").strip()
        if not action:
            return False
        key = (ms_id, action)
        if key not in type_cache:
            type_cache[key] = rbac.can(actor, action, ms_id)
        return type_cache[key]

    def _member(ms_id):
        if ms_id not in member_cache:
            member_cache[ms_id] = is_active_member(actor, ms_id)
        return member_cache[ms_id]

    result = {}
    for machine in machines:
        ms_id = machine.makerspace_id
        admin = _manage(ms_id) or _type_mgr(
            ms_id, getattr(machine.machine_type, "managing_action", "")
        )
        level = op_levels.get(machine.pk) if _member(ms_id) else None
        can_edit = admin or level in {MANAGE, FULL}
        result[machine.pk] = {
            "can_operate": can_edit or level is not None,
            "can_edit": can_edit,
            "can_delegate": admin or level == FULL,
            "can_retire": admin or level == FULL,
            "can_unretire": admin,
        }
    return result


def can_assign_operator(actor, machine, target_level, existing_level=None):
    """Whether `actor` may create/change an operator row at `target_level`.

    - Admin/type-manager: may set any level (including full).
    - A full operator: may assign/remove only operate|manage, and may NOT touch a full row.
      This prevents a full operator from minting more co-administrators.
    """
    if is_machine_admin(actor, machine):
        return True
    if not is_full_operator(actor, machine):
        return False
    if target_level == FULL or existing_level == FULL:
        return False
    return True


# --- List scoping ------------------------------------------------------------

def scope_machines_for_actor(actor, queryset):
    """Machines the actor may see: union of MANAGE_MACHINES labs, type-managed
    machines (via managing_action), and explicitly-assigned operator machines.
    Starts from membership + hard-hide + archived scope (via rbac helpers)."""
    from django.db.models import Q

    if actor is None or not getattr(actor, "is_authenticated", False):
        return queryset.none()

    manage_scope = rbac.makerspaces_for_action(actor, Action.MANAGE_MACHINES)
    if manage_scope is rbac.ALL:
        return queryset  # global superadmin (no hidden/archived) — unrestricted

    q = Q(makerspace_id__in=manage_scope) if manage_scope else Q(pk__in=[])

    for action in _managing_actions():
        tscope = rbac.makerspaces_for_action(actor, action)
        if tscope is rbac.ALL:
            q |= Q(machine_type__managing_action=action)
        elif tscope:
            q |= Q(machine_type__managing_action=action, makerspace_id__in=tscope)

    member_ms = rbac._exclude_archived_ids(
        set(actor.makerspace_memberships.values_list("makerspace_id", flat=True))
    )
    if member_ms:
        op_ids = MachineOperator.objects.filter(
            user=actor, machine__makerspace_id__in=member_ms
        ).values_list("machine_id", flat=True)
        q |= Q(pk__in=list(op_ids))

    return queryset.filter(q).distinct()


def scope_manageable_machines_for_actor(actor, queryset):
    """Machines whose warranty the actor may manage, entirely at query level.

    Includes machine admins, type managers, and active manage/full operators.
    Operate-only assignments are deliberately excluded from warranty reporting.
    """
    from django.db.models import Q

    if actor is None or not getattr(actor, "is_authenticated", False):
        return queryset.none()

    queryset = rbac.scope_by_makerspace(actor, queryset)
    manage_scope = rbac.makerspaces_for_action(actor, Action.MANAGE_MACHINES)
    if manage_scope is rbac.ALL:
        return queryset

    q = Q(makerspace_id__in=manage_scope) if manage_scope else Q(pk__in=[])
    for action in _managing_actions():
        type_scope = rbac.makerspaces_for_action(actor, action)
        if type_scope is rbac.ALL:
            q |= Q(machine_type__managing_action=action)
        elif type_scope:
            q |= Q(
                machine_type__managing_action=action,
                makerspace_id__in=type_scope,
            )

    if (
        getattr(actor, "is_active", False)
        and getattr(actor, "access_status", None) == User.AccessStatus.ACTIVE
    ):
        member_ms = rbac._exclude_archived_ids(
            set(actor.makerspace_memberships.values_list("makerspace_id", flat=True))
        )
        operator_ids = MachineOperator.objects.filter(
            user=actor,
            access_level__in=(MANAGE, FULL),
            machine__makerspace_id__in=member_ms,
        ).values_list("machine_id", flat=True)
        q |= Q(pk__in=operator_ids)

    return queryset.filter(q).distinct()


def can_see_machines(actor, makerspace_id):
    """Server-derived capability for the Machines tab within one makerspace."""
    if rbac.can(actor, Action.MANAGE_MACHINES, makerspace_id):
        return True
    for action in _managing_actions():
        if rbac.can(actor, action, makerspace_id):
            return True
    if is_active_member(actor, makerspace_id):
        return MachineOperator.objects.filter(
            user=actor, machine__makerspace_id=makerspace_id
        ).exists()
    return False


def _managing_actions():
    return list(
        MachineType.objects.exclude(managing_action="")
        .values_list("managing_action", flat=True)
        .distinct()
    )
