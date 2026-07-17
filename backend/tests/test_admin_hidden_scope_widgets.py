import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.accounts.models import User
from apps.makerspaces.models import Makerspace


pytestmark = pytest.mark.django_db


def test_makerspace_admin_lists_superadmin_status_and_frontend_mode():
    makerspace = Makerspace.objects.create(
        name="Mode Visible", slug="mode-visible", superadmin_access_enabled=False,
        frontend_domain="mode-visible.example",
    )
    model_admin = admin.site._registry[Makerspace]
    assert "location" in model_admin.list_display
    assert "superadmin_access" in model_admin.list_display
    assert "superadmin_access_enabled" not in model_admin.list_display
    assert "superadmin_access_enabled" in model_admin.list_filter
    assert model_admin.superadmin_access(makerspace) == "No"
    assert "frontend_mode" in model_admin.list_display
    assert model_admin.frontend_mode(makerspace) == "single-tenant"


def test_makerspace_fk_widget_excludes_hidden_makerspace():
    from apps.apiclients.models import ApiClient

    hidden_space = Makerspace.objects.create(
        name="Hidden FK", slug="hidden-fk-widget", superadmin_access_enabled=False,
    )
    visible_space = Makerspace.objects.create(name="Visible FK", slug="visible-fk-widget")
    superadmin = get_user_model().objects.create_user(
        username="fk-widget-superadmin", email="fk-widget-superadmin@example.com",
        password="test-pass", role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE, is_staff=True, is_superuser=True,
    )
    request = RequestFactory().get("/control/apiclients/apiclient/add/")
    request.user = superadmin
    model_admin = admin.site._registry[ApiClient]
    formfield = model_admin.formfield_for_foreignkey(ApiClient._meta.get_field("makerspace"), request)
    ids = set(formfield.queryset.values_list("id", flat=True))
    assert hidden_space.id not in ids
    assert visible_space.id in ids
