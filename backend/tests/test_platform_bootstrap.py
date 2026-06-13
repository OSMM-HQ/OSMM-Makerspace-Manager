import pytest
from rest_framework.test import APIClient

from apps.makerspaces.models import TenantFrontend
from tests.return_helpers import make_product, make_space

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
