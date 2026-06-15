import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.makerspaces.models import Makerspace, MakerspaceMembership, TenantFrontend

pytestmark = pytest.mark.django_db
LOGIN = "/api/v1/auth/login"


@pytest.fixture(autouse=True)
def _allow_test_origin(settings):
    # The container env sets CORS_ALLOWED_ORIGINS without :5000; pin it here so the
    # CSRF Origin check is deterministic regardless of deployment env. Reject-origin
    # tests still reject (evil/look-alike origins are not in this list).
    settings.CORS_ALLOWED_ORIGINS = ["http://localhost:5000"]


def make_staff(username="boss", role=User.Role.SPACE_MANAGER, password="pw-strong-123", **kw):
    return get_user_model().objects.create_user(
        username=username, email=f"{username}@e.com", password=password, role=role, **kw
    )


def test_login_returns_access_and_sets_refresh_cookie():
    user = make_staff()
    s = Makerspace.objects.create(name="Lab", slug="lab")
    MakerspaceMembership.objects.create(user=user, makerspace=s, role="space_manager")
    client = APIClient()

    resp = client.post(LOGIN, {"username": "boss", "password": "pw-strong-123"}, format="json")

    assert resp.status_code == 200
    assert "access" in resp.data
    assert "refresh" not in resp.data  # refresh lives in the cookie, never the body
    assert resp.data["user"]["role"] == "space_manager"
    assert resp.data["user"]["makerspaces"][0]["slug"] == "lab"
    assert "refresh_token" in resp.cookies
    assert resp.cookies["refresh_token"]["httponly"] is True


def test_login_rejects_bad_password():
    make_staff()
    resp = APIClient().post(LOGIN, {"username": "boss", "password": "wrong"}, format="json")
    assert resp.status_code == 401


def test_login_rejects_suspended_account():
    make_staff(username="bad", access_status=User.AccessStatus.SUSPENDED)
    resp = APIClient().post(LOGIN, {"username": "bad", "password": "pw-strong-123"}, format="json")
    assert resp.status_code in (401, 403)


REFRESH = "/api/v1/auth/refresh"
ALLOWED_ORIGIN = "http://localhost:5000"  # in CORS_ALLOWED_ORIGINS default


def _login(client, username="boss"):
    make_staff(username=username)
    return client.post(LOGIN, {"username": username, "password": "pw-strong-123"}, format="json")


def _csrf_headers():
    # Header presence forces CORS preflight; Origin must be allowlisted.
    return {"HTTP_X_REFRESH_CSRF": "1", "HTTP_ORIGIN": ALLOWED_ORIGIN}


def test_refresh_rejected_without_csrf_header():
    client = APIClient()
    _login(client)
    resp = client.post(REFRESH, HTTP_ORIGIN=ALLOWED_ORIGIN)  # header missing
    assert resp.status_code == 403


def test_refresh_rejected_from_unknown_origin():
    client = APIClient()
    _login(client)
    resp = client.post(REFRESH, HTTP_X_REFRESH_CSRF="1", HTTP_ORIGIN="https://evil.test")
    assert resp.status_code == 403


def test_refresh_rejected_on_origin_prefix_bypass():
    # Exact-match guard: a look-alike host must not pass (re-review fix).
    client = APIClient()
    _login(client)
    resp = client.post(
        REFRESH, HTTP_X_REFRESH_CSRF="1", HTTP_ORIGIN="http://localhost:5000.evil.test"
    )
    assert resp.status_code == 403


def test_refresh_allows_registered_staff_frontend_origin():
    registered_origin = "https://staff.example"
    makerspace = Makerspace.objects.create(name="Registered", slug="registered")
    TenantFrontend.objects.create(
        makerspace=makerspace,
        allowed_origins=[registered_origin],
        frontend_type=TenantFrontend.FrontendType.STAFF_ADMIN,
        is_active=True,
    )
    client = APIClient()
    _login(client)

    resp = client.post(
        REFRESH,
        HTTP_X_REFRESH_CSRF="1",
        HTTP_ORIGIN=registered_origin,
    )

    assert resp.status_code == 200
    assert "access" in resp.data
    assert "refresh_token" in resp.cookies


def test_refresh_rejects_public_and_integration_origins():
    """A public-portal frontend origin and a makerspace public/API-client origin must NOT
    pass the refresh CSRF check, even though both are 'registered' for CORS — otherwise a
    page on a public/integration origin could read a staff access token."""
    public_origin = "https://public.example"
    api_origin = "https://api-client.example"
    makerspace = Makerspace.objects.create(
        name="Public", slug="public-origins", cors_allowed_origins=[api_origin]
    )
    TenantFrontend.objects.create(
        makerspace=makerspace,
        allowed_origins=[public_origin],
        frontend_type=TenantFrontend.FrontendType.PUBLIC_PORTAL,
        is_active=True,
    )
    client = APIClient()
    _login(client)

    for origin in (public_origin, api_origin):
        resp = client.post(REFRESH, HTTP_X_REFRESH_CSRF="1", HTTP_ORIGIN=origin)
        assert resp.status_code == 403, origin


def test_refresh_rejects_unregistered_origin_with_csrf_header():
    Makerspace.objects.create(name="Registered", slug="registered-origin-reject")
    client = APIClient()
    _login(client)

    resp = client.post(
        REFRESH,
        HTTP_X_REFRESH_CSRF="1",
        HTTP_ORIGIN="https://unregistered.example",
    )

    assert resp.status_code == 403


def test_refresh_rotates_and_returns_new_access():
    client = APIClient()
    _login(client)
    resp = client.post(REFRESH, **_csrf_headers())
    assert resp.status_code == 200
    assert "access" in resp.data
    assert "refresh_token" in resp.cookies  # rotated


def test_old_refresh_rejected_after_rotation():
    client = APIClient()
    _login(client)
    old_refresh = client.cookies["refresh_token"].value
    assert client.post(REFRESH, **_csrf_headers()).status_code == 200  # rotates
    # Replay the OLD token - blacklist-after-rotation must reject it (review fix #6).
    replay = APIClient()
    replay.cookies["refresh_token"] = old_refresh
    resp = replay.post(REFRESH, **_csrf_headers())
    assert resp.status_code == 401


LOGOUT = "/api/v1/auth/logout"


def test_logout_clears_cookie_and_blocks_reuse():
    client = APIClient()
    _login(client)
    old_refresh = client.cookies["refresh_token"].value
    out = client.post(LOGOUT, **_csrf_headers())
    assert out.status_code == 200
    assert client.cookies["refresh_token"].value == ""  # cookie cleared

    # The blacklisted refresh token must no longer work (review fix #6).
    replay = APIClient()
    replay.cookies["refresh_token"] = old_refresh
    resp = replay.post(REFRESH, **_csrf_headers())
    assert resp.status_code == 401


def test_logout_rejected_without_csrf_header():
    client = APIClient()
    _login(client)
    resp = client.post(LOGOUT, HTTP_ORIGIN=ALLOWED_ORIGIN)  # header missing
    assert resp.status_code == 403


ME = "/api/v1/auth/me"


def test_me_requires_auth_and_returns_profile():
    client = APIClient()
    assert client.get(ME).status_code == 401
    login = _login(client, username="meuser")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    resp = client.get(ME)
    assert resp.status_code == 200
    assert resp.data["username"] == "meuser"
    assert resp.data["role"] == "space_manager"
