import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.admin_api.serializers_makerspaces import TenantFrontendSerializer
from apps.accounts.models import User
from apps.makerspaces.models import MakerspaceMembership, TenantFrontend
from tests.return_helpers import make_member, make_product, make_space, make_user

pytestmark = pytest.mark.django_db


def test_bootstrap_resolves_active_tenant_frontend_without_private_fields():
    makerspace = make_space("platform-a")
    makerspace.enabled_modules = ["public_inventory", "request_workflow"]
    makerspace.theme_config = {"primary_color": "#111111"}
    makerspace.branding_config = {"display_name": "Platform A"}
    makerspace.save()
    frontend = TenantFrontend.objects.create(
        makerspace=makerspace,
        token="tenant-token-a",
        frontend_type=TenantFrontend.FrontendType.KIOSK,
        allowed_origins=["https://kiosk.example"],
        is_primary=True,
    )

    response = APIClient().get(f"/api/v1/bootstrap?tenant={frontend.token}")

    assert response.status_code == 200
    assert response.data["makerspace"]["slug"] == makerspace.slug
    assert response.data["frontend"]["type"] == "kiosk"
    assert response.data["branding"]["display_name"] == "Platform A"
    assert response.data["public_api"]["publishable_key"] == makerspace.public_api_key
    assert "telegram_bot_token" not in response.data
    assert "request_submit" in response.data["workflows"]


def test_bootstrap_denies_inactive_frontend_token():
    makerspace = make_space("platform-inactive")
    TenantFrontend.objects.create(
        makerspace=makerspace,
        token="inactive-token",
        is_active=False,
    )

    response = APIClient().get("/api/v1/bootstrap?tenant=inactive-token")

    assert response.status_code == 404


@override_settings(API_CLIENT_AUTH_REQUIRED=True)
def test_publishable_key_cannot_cross_makerspace_slug():
    source = make_space("platform-key-source")
    target = make_space("platform-key-target")
    source.cors_allowed_origins = ["https://source.example"]
    target.cors_allowed_origins = ["https://target.example"]
    source.save(update_fields=["cors_allowed_origins"])
    target.save(update_fields=["cors_allowed_origins"])
    make_product(target)

    response = APIClient().get(
        f"/api/v1/public/{target.slug}/inventory/",
        HTTP_ORIGIN="https://source.example",
        HTTP_X_PUBLISHABLE_KEY=source.public_api_key,
    )

    assert response.status_code == 401


def test_disabled_request_module_blocks_public_submit():
    makerspace = make_space("platform-modules")
    makerspace.enabled_modules = ["public_inventory"]
    makerspace.save(update_fields=["enabled_modules"])
    product = make_product(makerspace)

    response = APIClient().post(
        f"/api/v1/public/{makerspace.slug}/requests",
        {
            "identifier": "member@example.com",
            "contact_email": "member@example.com",
            "contact_phone": "",
            "requested_for": "Testing",
            "items": [{"product_id": product.id, "quantity": 1}],
        },
        format="json",
    )

    assert response.status_code == 400
    assert "request_workflow" in str(response.data)


def test_tenant_frontend_serializer_accepts_one_bare_origin():
    makerspace = make_space("platform-origin-one")
    serializer = TenantFrontendSerializer(
        data={
            "makerspace": makerspace.id,
            "frontend_type": TenantFrontend.FrontendType.STAFF_ADMIN,
            "hostname": "https://AlphaMakerspace.com",
            "allowed_origins": ["https://AlphaMakerspace.com"],
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["hostname"] == "alphamakerspace.com"
    assert serializer.validated_data["allowed_origins"] == ["https://alphamakerspace.com"]


def test_tenant_frontend_serializer_rejects_path_origins():
    makerspace = make_space("platform-origin-path")
    serializer = TenantFrontendSerializer(
        data={
            "makerspace": makerspace.id,
            "frontend_type": TenantFrontend.FrontendType.STAFF_ADMIN,
            "hostname": "alphamakerspace.com",
            "allowed_origins": ["https://alphamakerspace.com/admin"],
        }
    )

    assert not serializer.is_valid()
    assert "allowed_origins" in serializer.errors


def test_tenant_frontend_serializer_rejects_multiple_origins():
    makerspace = make_space("platform-origin-many")
    serializer = TenantFrontendSerializer(
        data={
            "makerspace": makerspace.id,
            "frontend_type": TenantFrontend.FrontendType.STAFF_ADMIN,
            "hostname": "alphamakerspace.com",
            "allowed_origins": [
                "https://alphamakerspace.com",
                "https://staff.alphamakerspace.com",
            ],
        }
    )

    assert not serializer.is_valid()
    assert "allowed_origins" in serializer.errors


def test_space_manager_can_register_frontend_for_superadmin_hidden_makerspace():
    makerspace = make_space("platform-hidden-self-serve")
    makerspace.superadmin_access_enabled = False
    makerspace.save(update_fields=["superadmin_access_enabled"])
    manager = make_member("hidden-frontend-manager", makerspace)
    client = APIClient()
    client.force_authenticate(manager)

    response = client.post(
        f"/api/v1/admin/makerspace/{makerspace.id}/frontends",
        {
            "frontend_type": TenantFrontend.FrontendType.STAFF_ADMIN,
            "hostname": "hidden.example",
            "allowed_origins": ["https://hidden.example"],
            "enabled_modules": [],
            "is_primary": True,
            "is_active": True,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["token"]


def test_superadmin_cannot_register_frontend_for_superadmin_hidden_makerspace():
    makerspace = make_space("platform-hidden-superadmin-blocked")
    make_member("platform-hidden-superadmin-blocked-manager", makerspace)
    makerspace.superadmin_access_enabled = False
    makerspace.save(update_fields=["superadmin_access_enabled"])
    superadmin = make_user(
        "hidden-frontend-superadmin",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
        is_staff=True,
        is_superuser=True,
    )
    client = APIClient()
    client.force_authenticate(superadmin)

    response = client.post(
        f"/api/v1/admin/makerspace/{makerspace.id}/frontends",
        {
            "frontend_type": TenantFrontend.FrontendType.STAFF_ADMIN,
            "hostname": "hidden-superadmin.example",
            "allowed_origins": ["https://hidden-superadmin.example"],
            "enabled_modules": [],
            "is_primary": True,
            "is_active": True,
        },
        format="json",
    )

    assert response.status_code == 403


def test_staff_origin_scope_filters_makerspace_list_and_blocks_cross_tenant_targets():
    origin = "https://space-a.example"
    space_a = make_space("platform-origin-scope-a")
    space_b = make_space("platform-origin-scope-b")
    product_a = make_product(space_a, name="Scope A")
    product_b = make_product(space_b, name="Scope B")
    staff = make_user(
        "origin-scope-staff",
        role=User.Role.SPACE_MANAGER,
        access_status=User.AccessStatus.ACTIVE,
    )
    MakerspaceMembership.objects.create(
        user=staff,
        makerspace=space_a,
        role=MakerspaceMembership.Role.SPACE_MANAGER,
    )
    MakerspaceMembership.objects.create(
        user=staff,
        makerspace=space_b,
        role=MakerspaceMembership.Role.SPACE_MANAGER,
    )
    TenantFrontend.objects.create(
        makerspace=space_a,
        frontend_type=TenantFrontend.FrontendType.STAFF_ADMIN,
        allowed_origins=[origin],
        is_active=True,
    )
    client = APIClient()
    client.force_authenticate(staff)

    listed = client.get("/api/v1/admin/makerspaces", HTTP_ORIGIN=origin)
    own_list = client.get(
        f"/api/v1/admin/makerspace/{space_a.id}/inventory",
        HTTP_ORIGIN=origin,
    )
    cross_list = client.get(
        f"/api/v1/admin/makerspace/{space_b.id}/inventory",
        HTTP_ORIGIN=origin,
    )
    own_detail = client.get(f"/api/v1/admin/inventory/{product_a.id}", HTTP_ORIGIN=origin)
    cross_detail = client.get(
        f"/api/v1/admin/inventory/{product_b.id}",
        HTTP_ORIGIN=origin,
    )

    assert listed.status_code == 200
    assert [row["id"] for row in listed.data] == [space_a.id]
    assert own_list.status_code == 200
    assert cross_list.status_code == 403
    assert own_detail.status_code == 200
    assert cross_detail.status_code == 403
