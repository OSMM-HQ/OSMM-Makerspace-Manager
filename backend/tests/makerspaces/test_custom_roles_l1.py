import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError

from apps.accounts.models import User
from apps.makerspaces import roles
from apps.makerspaces.models import Makerspace, MakerspaceMembership, MakerspaceRole


LEGACY_ROLE_VALUES = [definition[0] for definition in roles.DEFAULT_ROLE_DEFINITIONS]
HISTORICAL_ROLE_VALUES = [*LEGACY_ROLE_VALUES, MakerspaceMembership.Role.PRINT_MANAGER]


def make_user(username):
    return User.objects.create_user(username=username, password="password")


def assert_default_roles(makerspace):
    actual = {
        role.legacy_role: role
        for role in MakerspaceRole.objects.filter(makerspace=makerspace)
    }
    assert set(actual) == set(LEGACY_ROLE_VALUES) | {None}
    for legacy_role, name, granted_actions in roles.DEFAULT_ROLE_DEFINITIONS:
        role = actual[legacy_role]
        assert role.name == name
        assert role.slug == legacy_role
        assert role.granted_actions == sorted(granted_actions)
        assert role.is_default is True
        assert role.is_protected is True
    member = actual[None]
    assert member.name == "Member"
    assert member.slug == "member"
    assert member.granted_actions == []
    assert member.is_default is True
    assert member.is_protected is True


@pytest.mark.django_db(transaction=True)
def test_new_makerspace_gets_protected_default_roles():
    makerspace = Makerspace.objects.create(name="New roles", slug="new-roles")

    assert_default_roles(makerspace)


@pytest.mark.django_db(transaction=True)
def test_ensure_default_roles_is_idempotent():
    makerspace = Makerspace.objects.create(name="Idempotent roles", slug="idempotent-roles")

    roles.ensure_default_roles(makerspace)
    roles.ensure_default_roles(makerspace)

    assert MakerspaceRole.objects.filter(makerspace=makerspace).count() == 5
    assert_default_roles(makerspace)


@pytest.mark.django_db(transaction=True)
def test_seed_and_backfill_migration_round_trip():
    from_target = [("makerspaces", "0037_makerspace_mattermost_webhook_url_and_more")]
    schema_target = [("makerspaces", "0038_makerspace_roles")]
    target = [("makerspaces", "0039_seed_and_backfill_roles")]
    executor = MigrationExecutor(connection)
    makerspace_id = None

    try:
        executor.migrate(from_target)
        old_apps = executor.loader.project_state(from_target).apps
        OldMakerspace = old_apps.get_model("makerspaces", "Makerspace")
        OldMembership = old_apps.get_model("makerspaces", "MakerspaceMembership")
        makerspace = OldMakerspace.objects.create(
            name="Migrated roles", slug="migrated-roles"
        )
        makerspace_id = makerspace.id
        memberships = {}
        for index, legacy_role in enumerate(HISTORICAL_ROLE_VALUES):
            user = make_user(f"migration-role-{index}")
            membership = OldMembership.objects.create(
                makerspace_id=makerspace.id,
                user_id=user.id,
                role=legacy_role,
            )
            memberships[legacy_role] = membership.id

        executor = MigrationExecutor(connection)
        executor.migrate(target)
        new_apps = executor.loader.project_state(target).apps
        NewMakerspaceRole = new_apps.get_model("makerspaces", "MakerspaceRole")
        NewMembership = new_apps.get_model("makerspaces", "MakerspaceMembership")
        seeded = {
            role.legacy_role: role
            for role in NewMakerspaceRole.objects.filter(makerspace_id=makerspace.id)
        }
        assert set(seeded) == set(HISTORICAL_ROLE_VALUES)
        assert seeded[MakerspaceMembership.Role.PRINT_MANAGER].granted_actions == ["manage_printing"]
        for legacy_role, name, granted_actions in roles.DEFAULT_ROLE_DEFINITIONS:
            role = seeded[legacy_role]
            assert role.name == name
            assert role.slug == legacy_role
            assert role.granted_actions == sorted(granted_actions)
            assert role.is_default is True
            assert role.is_protected is True
            membership = NewMembership.objects.get(id=memberships[legacy_role])
            assert membership.assigned_role_id == role.id

        executor = MigrationExecutor(connection)
        executor.migrate(schema_target)
        schema_apps = executor.loader.project_state(schema_target).apps
        SchemaMakerspaceRole = schema_apps.get_model("makerspaces", "MakerspaceRole")
        SchemaMembership = schema_apps.get_model("makerspaces", "MakerspaceMembership")
        assert not SchemaMakerspaceRole.objects.filter(makerspace_id=makerspace.id).exists()
        for legacy_role, membership_id in memberships.items():
            membership = SchemaMembership.objects.get(id=membership_id)
            assert membership.assigned_role_id is None
            assert membership.role == legacy_role
    finally:
        # Restore the FULL migration graph forward, not just makerspaces/0039.
        # Rewinding makerspaces to 0037 cascade-unapplies migrations in other apps
        # that depend on makerspaces/0039 (e.g. encryption/0001), and migrating only
        # makerspaces forward would leave those dropped tables missing for every
        # later test in the process.
        #
        # Remove this historical fixture first: printing/0022 is fail-closed and
        # correctly rejects any unflipped makerspace while retiring its legacy
        # tables. Raw SQL avoids loading current related models whose tables are
        # intentionally absent at `schema_target`.
        if makerspace_id is not None:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM makerspaces_makerspacemembership WHERE makerspace_id = %s",
                    [makerspace_id],
                )
                cursor.execute(
                    "DELETE FROM makerspaces_makerspace WHERE id = %s",
                    [makerspace_id],
                )
        restore = MigrationExecutor(connection)
        restore.migrate(restore.loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_seeded_defaults_match_frozen_rbac_mapping():
    from apps.accounts import rbac

    makerspace = Makerspace.objects.create(name="Parity roles", slug="parity-roles")
    seeded = {
        role.legacy_role: role.granted_actions
        for role in MakerspaceRole.objects.filter(makerspace=makerspace)
    }

    assert set(seeded) == set(LEGACY_ROLE_VALUES) | {None}
    for legacy_role, _name, actions in roles.DEFAULT_ROLE_DEFINITIONS:
        assert seeded[legacy_role] == sorted(actions)
    assert seeded[None] == []


@pytest.mark.django_db(transaction=True)
def test_role_constraints_protect_and_custom_membership_choice():
    makerspace = Makerspace.objects.create(name="Role constraints", slug="role-constraints")
    role = MakerspaceRole.objects.create(
        makerspace=makerspace,
        name="Borrow Desk",
        slug="borrow-desk",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        MakerspaceRole.objects.create(
            makerspace=makerspace,
            name="borrow desk",
            slug="borrow-desk-two",
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        MakerspaceRole.objects.create(
            makerspace=makerspace,
            name="Borrow Desk Two",
            slug="BORROW-DESK",
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        MakerspaceRole.objects.create(
            makerspace=makerspace,
            name="Duplicate legacy",
            slug="duplicate-legacy",
            legacy_role=MakerspaceMembership.Role.SPACE_MANAGER,
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        MakerspaceRole.objects.create(
            makerspace=makerspace,
            name="Invalid default",
            slug="invalid-default",
            is_default=True,
        )

    membership = MakerspaceMembership.objects.create(
        makerspace=makerspace,
        user=make_user("protected-role-user"),
        assigned_role=role,
    )
    with pytest.raises(ProtectedError):
        role.delete()

    custom_membership = MakerspaceMembership.objects.create(
        makerspace=makerspace,
        user=make_user("custom-role-user"),
        role=MakerspaceMembership.Role.CUSTOM,
    )
    assert membership.assigned_role_id == role.id
    assert custom_membership.role == "custom"


def test_role_save_trims_and_rejects_blank_names():
    role = MakerspaceRole(name="   ", slug="blank")

    with pytest.raises(ValidationError):
        role.save()


@pytest.mark.django_db(transaction=True)
def test_membership_clean_rejects_cross_tenant_assigned_role():
    space_a = Makerspace.objects.create(name="Tenant A", slug="tenant-a")
    space_b = Makerspace.objects.create(name="Tenant B", slug="tenant-b")
    role_b = MakerspaceRole.objects.create(
        makerspace=space_b, name="B Role", slug="b-role"
    )
    membership = MakerspaceMembership(
        makerspace=space_a,
        user=make_user("cross-tenant-user"),
        assigned_role=role_b,
    )
    with pytest.raises(ValidationError):
        membership.clean()
