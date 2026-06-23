import pytest
from django.test import override_settings
from rest_framework.test import APIClient, APIRequestFactory

from apps.accounts.models import User
from apps.makerspaces.cors import origin_is_registered, staff_origin_is_registered
from apps.makerspaces.models import MakerspaceMembership
from apps.makerspaces.origin_scope import NO_STAFF_ORIGIN_SCOPE, staff_origin_scope
from tests.return_helpers import make_member, make_product, make_space, make_user

pytestmark = pytest.mark.django_db


def test_bootstrap_resolves_public_code_without_private_fields():
    makerspace = make_space("platform-a")
    makerspace.enabled_modules = ["public_inventory", "request_workflow"]
    makerspace.theme_config = {"primary_color": "#111111"}
    makerspace.branding_config = {"display_name": "Platform A"}
    makerspace.frontend_domain = "platform-a.example"
    makerspace.cors_allowed_origins = ["https://api-client.example"]
    makerspace.save()

    response = APIClient().get(f"/api/v1/bootstrap?tenant={makerspace.public_code}")

    assert response.status_code == 200
    assert response.data["makerspace"]["slug"] == makerspace.slug
    assert response.data["frontend"]["type"] == "makerspace"
    assert response.data["frontend"]["hostname"] == "platform-a.example"
    assert response.data["frontend"]["allowed_origins"] == [
        "https://api-client.example",
        "https://platform-a.example",
    ]
    assert response.data["branding"]["display_name"] == "Platform A"
    assert response.data["public_api"]["publishable_key"] == makerspace.public_api_key
    assert "telegram_bot_token" not in response.data
    assert "request_submit" in response.data["workflows"]


def test_bootstrap_resolves_by_frontend_domain_origin():
    makerspace = make_space("platform-origin")
    makerspace.frontend_domain = "origin.example"
    makerspace.save(update_fields=["frontend_domain"])

    response = APIClient().get("/api/v1/bootstrap", HTTP_ORIGIN="https://origin.example")

    assert response.status_code == 200
    assert response.data["makerspace"]["slug"] == makerspace.slug


def test_bootstrap_resolves_by_slug():
    makerspace = make_space("platform-slug")

    response = APIClient().get(f"/api/v1/bootstrap?slug={makerspace.slug}")

    assert response.status_code == 200
    assert response.data["makerspace"]["public_code"] == makerspace.public_code


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


@override_settings(API_CLIENT_AUTH_REQUIRED=True)
def test_public_only_cors_origin_allows_public_api_but_not_staff_scope():
    public_origin = "https://public-api.example"
    makerspace = make_space("platform-public-origin")
    makerspace.cors_allowed_origins = [public_origin]
    makerspace.save(update_fields=["cors_allowed_origins"])
    make_product(makerspace)

    response = APIClient().get(
        f"/api/v1/public/{makerspace.slug}/inventory/",
        HTTP_ORIGIN=public_origin,
        HTTP_X_PUBLISHABLE_KEY=makerspace.public_api_key,
    )
    request = APIRequestFactory().get("/api/v1/admin/makerspaces", HTTP_ORIGIN=public_origin)

    assert response.status_code == 200
    assert origin_is_registered(public_origin) is True
    assert staff_origin_is_registered(public_origin) is False
    assert staff_origin_scope(request) is NO_STAFF_ORIGIN_SCOPE


def test_disabled_request_module_blocks_public_submit():
    makerspace = make_space("platform-modules")
    makerspace.enabled_modules = ["public_inventory"]
    makerspace.save(update_fields=["enabled_modules"])
    product = make_product(makerspace)

    response = APIClient().post(
        f"/api/v1/public/{makerspace.slug}/requests",
        {
            "requester_name": "Module Test Member",
            "contact_email": "member@example.com",
            "contact_phone": "+15550101010",
            "requested_for": "Testing",
            "items": [{"product_id": product.id, "quantity": 1}],
        },
        format="json",
    )

    assert response.status_code == 400
    assert "request_workflow" in str(response.data)


def test_space_manager_can_update_frontend_domain_for_superadmin_hidden_makerspace():
    makerspace = make_space("platform-hidden-self-serve")
    makerspace.superadmin_access_enabled = False
    makerspace.save(update_fields=["superadmin_access_enabled"])
    manager = make_member("hidden-frontend-manager", makerspace)
    client = APIClient()
    client.force_authenticate(manager)

    response = client.patch(
        f"/api/v1/admin/makerspaces/{makerspace.id}",
        {
            "frontend_domain": "hidden.example",
            "hidden_from_central_directory": True,
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["frontend_domain"] == "hidden.example"
    assert response.data["hidden_from_central_directory"] is True


def test_superadmin_cannot_update_frontend_domain_for_superadmin_hidden_makerspace():
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

    response = client.patch(
        f"/api/v1/admin/makerspaces/{makerspace.id}",
        {
            "frontend_domain": "hidden-superadmin.example",
        },
        format="json",
    )

    assert response.status_code == 404
    makerspace.refresh_from_db()
    assert makerspace.frontend_domain is None


def test_staff_origin_scope_filters_makerspace_list_and_blocks_cross_tenant_targets():
    origin = "https://space-a.example"
    space_a = make_space("platform-origin-scope-a")
    space_b = make_space("platform-origin-scope-b")
    space_a.frontend_domain = "space-a.example"
    space_a.save(update_fields=["frontend_domain"])
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
