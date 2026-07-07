from types import SimpleNamespace

import pytest

from apps.makerspaces.cors import cors_allow_registered_frontend
from tests.return_helpers import make_space

pytestmark = pytest.mark.django_db

PUBLIC_API_ORIGIN = "https://api-client.example.com"
STAFF_ORIGIN = "https://staff.example.com"
UNKNOWN_ORIGIN = "https://unknown.example.com"

STAFF_PATHS = [
    "/api/v1/auth/login",
    "/api/v1/auth/me",
    "/api/v1/admin/x",
    "/api/v1/guest-admin/x",
    "/api/v1/printing/manage/x",
    "/api/v1/printing/admin/x",
    "/api/v1/procurement/x",
    "/api/v1/integrations/telegram/test-alert",
]

PUBLIC_PATHS = [
    "/api/v1/public/x",
    "/api/v1/printing/public/x",
    "/api/v1/integrations/telegram/webhook",
]


def make_request(path, origin):
    return SimpleNamespace(path=path, headers={"Origin": origin})


def cors_allows(path, origin):
    return cors_allow_registered_frontend(None, make_request(path, origin))


@pytest.fixture
def makerspace_with_origins():
    makerspace = make_space("cors-firewall")
    makerspace.frontend_domain = "staff.example.com"
    makerspace.cors_allowed_origins = [PUBLIC_API_ORIGIN]
    makerspace.save(update_fields=["frontend_domain", "cors_allowed_origins"])
    return makerspace


@pytest.mark.parametrize("path", STAFF_PATHS)
def test_public_api_origin_is_blocked_on_staff_paths(makerspace_with_origins, path):
    assert cors_allows(path, PUBLIC_API_ORIGIN) is False


@pytest.mark.parametrize("path", PUBLIC_PATHS)
def test_public_api_origin_is_allowed_on_public_paths(makerspace_with_origins, path):
    assert cors_allows(path, PUBLIC_API_ORIGIN) is True


@pytest.mark.parametrize("path", STAFF_PATHS + PUBLIC_PATHS)
def test_registered_staff_origin_is_allowed_on_staff_and_public_paths(
    makerspace_with_origins,
    path,
):
    assert cors_allows(path, STAFF_ORIGIN) is True


@pytest.mark.parametrize("path", STAFF_PATHS + PUBLIC_PATHS)
def test_unknown_origin_is_blocked_everywhere(makerspace_with_origins, path):
    assert cors_allows(path, UNKNOWN_ORIGIN) is False
