import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.accounts.models import User
from apps.inventory.models import InventoryProduct
from apps.makerspaces.models import Makerspace, MakerspaceMembership, TenantFrontend
from config.admin_access import GLOBAL_ADMIN_MODELS

pytestmark = pytest.mark.django_db


def _makerspace_lookup_paths(model, max_depth=3):
    if model is Makerspace:
        return {"id"}

    paths = set()

    def walk(current_model, prefix, depth, seen):
        if depth > max_depth:
            return

        for field in current_model._meta.get_fields():
            if not getattr(field, "is_relation", False):
                continue
            if getattr(field, "auto_created", False) and not getattr(field, "concrete", False):
                continue
            if not (getattr(field, "many_to_one", False) or getattr(field, "one_to_one", False)):
                continue

            remote_field = getattr(field, "remote_field", None)
            related_model = getattr(remote_field, "model", None) if remote_field else None
            if related_model is None or isinstance(related_model, str):
                continue

            field_path = prefix + [field.name]
            if related_model is Makerspace:
                paths.add("__".join(field_path) + "_id")
            elif depth < max_depth and related_model not in seen:
                walk(related_model, field_path, depth + 1, seen | {related_model})

    walk(model, [], 1, {model})
    return paths


def test_every_registered_admin_resolves_a_makerspace_decision():
    failures = []

    for model, model_admin in sorted(
        admin.site._registry.items(),
        key=lambda item: item[0]._meta.label_lower,
    ):
        model_key = f"{model._meta.app_label}.{model._meta.model_name}"
        lookup = (
            model_admin.resolve_hidden_lookup()
            if hasattr(model_admin, "resolve_hidden_lookup")
            else None
        )
        paths = _makerspace_lookup_paths(model)

        if model_key in GLOBAL_ADMIN_MODELS:
            if lookup is not None:
                failures.append(
                    f"{model_key}: listed GLOBAL_ADMIN_MODELS but resolved {lookup!r}"
                )
            continue

        if paths:
            if lookup is None:
                failures.append(
                    f"{model_key}: reaches Makerspace via {sorted(paths)} but resolved None"
                )
            elif lookup not in paths:
                failures.append(
                    f"{model_key}: resolved {lookup!r}, expected one of {sorted(paths)}"
                )
        elif lookup is not None:
            failures.append(f"{model_key}: has no Makerspace path but resolved {lookup!r}")
        else:
            failures.append(
                f"{model_key}: has no Makerspace path and is missing from GLOBAL_ADMIN_MODELS"
            )

    assert not failures, "Admin hidden-scope drift:\n" + "\n".join(failures)


def test_inventory_product_admin_hides_disabled_makerspace_rows():
    hidden_space = Makerspace.objects.create(
        name="Hidden",
        slug="hidden-admin-scope",
        superadmin_access_enabled=False,
    )
    hidden_manager = get_user_model().objects.create_user(
        username="hidden-admin-scope-manager",
        email="hidden-admin-scope-manager@example.com",
        role=User.Role.SPACE_MANAGER,
        access_status=User.AccessStatus.ACTIVE,
    )
    MakerspaceMembership.objects.create(
        user=hidden_manager,
        makerspace=hidden_space,
        role=MakerspaceMembership.Role.SPACE_MANAGER,
    )
    visible_space = Makerspace.objects.create(
        name="Visible",
        slug="visible-admin-scope",
    )
    hidden_product = InventoryProduct.objects.create(
        makerspace=hidden_space,
        name="Hidden product",
    )
    visible_product = InventoryProduct.objects.create(
        makerspace=visible_space,
        name="Visible product",
    )
    superadmin = get_user_model().objects.create_user(
        username="scope-superadmin",
        email="scope-superadmin@example.com",
        password="test-pass",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
        is_staff=True,
        is_superuser=True,
    )
    request = RequestFactory().get("/control/inventory/inventoryproduct/")
    request.user = superadmin

    queryset = admin.site._registry[InventoryProduct].get_queryset(request)

    assert hidden_product not in queryset
    assert visible_product in queryset


def test_makerspace_admin_lists_disabled_makerspace_for_governance_visibility():
    hidden_space = Makerspace.objects.create(
        name="Hidden",
        slug="hidden-admin-visible",
        superadmin_access_enabled=False,
    )
    visible_space = Makerspace.objects.create(
        name="Visible",
        slug="visible-admin-visible",
    )
    superadmin = get_user_model().objects.create_user(
        username="scope-visible-superadmin",
        email="scope-visible-superadmin@example.com",
        password="test-pass",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
        is_staff=True,
        is_superuser=True,
    )
    request = RequestFactory().get("/control/makerspaces/makerspace/")
    request.user = superadmin

    queryset = admin.site._registry[Makerspace].get_queryset(request)

    assert hidden_space in queryset
    assert visible_space in queryset


def test_makerspace_admin_lists_superadmin_status_and_frontend_mode():
    makerspace = Makerspace.objects.create(
        name="Mode Visible",
        slug="mode-visible",
        superadmin_access_enabled=False,
    )
    TenantFrontend.objects.create(
        makerspace=makerspace,
        frontend_type=TenantFrontend.FrontendType.STAFF_ADMIN,
        hostname="mode-visible.example",
        is_active=True,
    )
    model_admin = admin.site._registry[Makerspace]

    assert "location" in model_admin.list_display
    assert "superadmin_access_enabled" in model_admin.list_display
    assert "frontend_mode" in model_admin.list_display
    assert model_admin.frontend_mode(makerspace) == "single-tenant"
