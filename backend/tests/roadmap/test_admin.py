import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory
from django.urls import reverse
from unfold.admin import ModelAdmin

from apps.accounts.models import User
from apps.roadmap.admin import RoadmapItemAdmin
from apps.roadmap.models import RoadmapItem
from config.admin_access import (
    GLOBAL_ADMIN_MODELS,
    NESTED_MAKERSPACE_LOOKUPS,
    SuperuserOnlyModelAdmin,
)

pytestmark = pytest.mark.django_db


def make_user(username, **kwargs):
    defaults = {
        "email": f"{username}@example.com",
        "password": "test-pass",
        "access_status": User.AccessStatus.ACTIVE,
    }
    defaults.update(kwargs)
    return get_user_model().objects.create_user(username=username, **defaults)


def make_superadmin(username="roadmap-superadmin", **kwargs):
    return make_user(
        username,
        role=User.Role.SUPERADMIN,
        is_staff=True,
        is_superuser=True,
        **kwargs,
    )


def test_admin_is_registered_with_required_bases_and_configuration():
    model_admin = admin.site._registry[RoadmapItem]

    assert isinstance(model_admin, RoadmapItemAdmin)
    assert isinstance(model_admin, ModelAdmin)
    assert RoadmapItemAdmin.__bases__[0] is SuperuserOnlyModelAdmin
    assert model_admin.list_display == (
        "title",
        "status",
        "category",
        "order",
        "is_public",
        "published_at",
        "updated_at",
    )
    assert model_admin.list_filter == ("status", "is_public", "category")
    assert model_admin.search_fields == ("title", "description", "category")
    assert model_admin.list_editable == ("order", "is_public")
    assert model_admin.ordering == ("order", "-published_at", "id")
    assert model_admin.readonly_fields == ("created_at", "updated_at")

    request = RequestFactory().get("/control/roadmap/roadmapitem/add/")
    request.user = make_superadmin("roadmap-admin-form")
    fields = model_admin.get_form(request).base_fields
    assert {
        "title",
        "description",
        "status",
        "category",
        "order",
        "is_public",
        "published_at",
    } <= fields.keys()
    assert {"created_at", "updated_at"}.isdisjoint(fields)


def test_active_superadmin_can_crud_and_edit_all_editorial_states():
    client = Client(raise_request_exception=False)
    client.force_login(make_superadmin())
    changelist_url = reverse("admin:roadmap_roadmapitem_changelist")
    add_url = reverse("admin:roadmap_roadmapitem_add")

    assert client.get(changelist_url).status_code == 200
    assert client.get(add_url).status_code == 200
    added = client.post(
        add_url,
        {
            "title": "Roadmap CRUD",
            "description": "Created in the control plane",
            "status": RoadmapItem.Status.PLANNED,
            "category": "",
            "order": "0",
            "is_public": "on",
            "_save": "Save",
        },
    )
    assert added.status_code == 302

    item = RoadmapItem.objects.get(title="Roadmap CRUD")
    change_url = reverse("admin:roadmap_roadmapitem_change", args=[item.pk])
    for status in RoadmapItem.Status.values:
        changed = client.post(
            change_url,
            {
                "title": item.title,
                "description": item.description,
                "status": status,
                "category": "Platform",
                "order": "4",
                "is_public": "on",
                "published_at_0": "2026-07-16",
                "published_at_1": "10:30:00",
                "_save": "Save",
            },
        )
        assert changed.status_code == 302
        item.refresh_from_db()
        assert item.status == status
        assert item.is_public is True
        assert item.published_at is not None

    cleared = client.post(
        change_url,
        {
            "title": item.title,
            "description": item.description,
            "status": RoadmapItem.Status.PLANNED,
            "category": "",
            "order": "0",
            "_save": "Save",
        },
    )
    assert cleared.status_code == 302
    item.refresh_from_db()
    assert item.is_public is False
    assert item.published_at is None

    pinned = RoadmapItem.objects.create(
        title="Pinned", description="Details", order=-1
    )
    assert list(RoadmapItem.objects.all())[:2] == [pinned, item]

    delete_url = reverse("admin:roadmap_roadmapitem_delete", args=[item.pk])
    assert client.get(delete_url).status_code == 200
    assert client.post(delete_url, {"post": "yes"}).status_code == 302
    assert not RoadmapItem.objects.filter(pk=item.pk).exists()


def test_non_active_superadmin_variants_cannot_use_model_admin():
    users = [
        make_user(
            "roadmap-non-superuser",
            role=User.Role.SPACE_MANAGER,
            is_staff=True,
        ),
        make_superadmin("roadmap-inactive", is_active=False),
        make_superadmin(
            "roadmap-suspended",
            access_status=User.AccessStatus.SUSPENDED,
        ),
        make_superadmin("roadmap-forced-password", must_change_password=True),
    ]
    url = reverse("admin:roadmap_roadmapitem_changelist")

    assert Client().get(url).status_code == 302
    for user in users:
        client = Client(raise_request_exception=False)
        client.force_login(user)
        assert client.get(url).status_code in {302, 403}


def test_platform_scope_is_explicit_and_resolves_without_tenant_filter():
    model_admin = admin.site._registry[RoadmapItem]

    assert "roadmap.roadmapitem" in GLOBAL_ADMIN_MODELS
    assert "roadmap.roadmapitem" not in NESTED_MAKERSPACE_LOOKUPS
    assert model_admin.resolve_hidden_lookup() is None
