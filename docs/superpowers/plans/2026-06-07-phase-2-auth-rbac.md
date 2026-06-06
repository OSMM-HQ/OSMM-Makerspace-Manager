# Phase 2 — Auth + RBAC + Makerspace Scoping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In THIS repo, Stage-2 implementation is delegated to Codex per `~/.claude/CLAUDE.md`; Claude verifies each task group.

**Goal:** Staff (superadmin/admin/guest-admin) can log into a separate-origin frontend via JWT, and every staff query is permission-checked and scoped to assigned makerspaces.

**Architecture:** `djangorestframework-simplejwt` issues a short-lived access token (returned in the JSON body, held in browser memory) and a long-lived refresh token (set as a cross-site `HttpOnly; Secure; SameSite=None` cookie scoped to the refresh path, protected by a double-submit CSRF cookie/header). A single RBAC module (`apps/accounts/rbac.py`) owns the 4-role permission matrix and `scope_by_makerspace`; DRF permission classes + a queryset mixin reuse it. New surface mounts under `/api/v1/`; existing public routes are aliased there without breaking.

**Tech Stack:** Django 5.1, DRF, djangorestframework-simplejwt (+ token_blacklist), django-cors-headers, pytest-django; React 18 + TS + Vite + TanStack Query + react-router v6.

---

## File Structure

**Backend (`backend/`)**
- `requirements.txt` — add `djangorestframework-simplejwt`.
- `config/settings.py` — INSTALLED_APPS (+ simplejwt blacklist), REST_FRAMEWORK auth, SIMPLE_JWT, cookie/CSRF settings, `CORS_ALLOW_CREDENTIALS`.
- `config/urls.py` — mount `apps.accounts.urls` under `api/v1/auth/`; alias public routes under `api/v1/`.
- `apps/accounts/rbac.py` — `resolve_scope`, `scope_by_makerspace`, `can`, action constants. (new)
- `apps/accounts/permissions.py` — `IsSuperadmin`, `IsStaff`, `HasMakerspaceAction`, `MakerspaceScopedQuerysetMixin`. (new)
- `apps/accounts/auth_cookies.py` — `set_refresh_cookies`, `clear_refresh_cookies`. (new)
- `apps/accounts/serializers.py` — `LoginSerializer`, `user_payload`. (new)
- `apps/accounts/views.py` — `LoginView`, `RefreshView`, `LogoutView`, `MeView`. (new)
- `apps/accounts/urls.py` — auth routes. (new)
- `tests/test_rbac.py`, `tests/test_auth.py` — behavior tests. (new)

**Frontend (`frontend/`)**
- `src/features/auth/authApi.ts` — login/refresh/logout/me calls (credentials: include). (new)
- `src/features/auth/AuthContext.tsx` — in-memory access token + provider + `useAuth`. (new)
- `src/features/auth/LoginPage.tsx` — login form. (new)
- `src/features/auth/RequireAuth.tsx` — protected layout gated by `/me`. (new)
- `src/lib/authClient.ts` — fetch wrapper: attach Bearer, 401→refresh→retry. (new)
- `src/App.tsx` — add `/login` + protected `/admin` routes.
- `src/main.tsx` — wrap app in `AuthProvider`.

---

## Task 1: Dependencies + JWT/cookie/CORS settings

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/config/settings.py`

- [ ] **Step 1: Add the dependency**

In `backend/requirements.txt` add after the `drf-spectacular` line:

```
djangorestframework-simplejwt>=5.3
```

Install: `docker compose exec backend pip install "djangorestframework-simplejwt>=5.3"`

- [ ] **Step 2: Register apps**

In `config/settings.py` `INSTALLED_APPS`, add after `"drf_spectacular",`:

```python
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
```

- [ ] **Step 3: DRF auth + JWT + cookie/CSRF + CORS settings**

In `config/settings.py`, extend `REST_FRAMEWORK` and append new blocks. Add at top of file with the other imports:

```python
from datetime import timedelta
```

Update `REST_FRAMEWORK` to include:

```python
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 24,
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    # Public endpoints opt into AllowAny explicitly; staff views require auth + role.
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.AllowAny",),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# Cross-site refresh cookie (frontends live on separate origins).
AUTH_REFRESH_COOKIE = "refresh_token"
AUTH_CSRF_COOKIE = "refresh_csrf"          # readable double-submit token
AUTH_CSRF_HEADER = "X-Refresh-CSRF"        # client echoes the csrf cookie here
AUTH_COOKIE_PATH = "/api/v1/auth/"
AUTH_COOKIE_SECURE = env.bool("AUTH_COOKIE_SECURE", default=not DEBUG)
AUTH_COOKIE_SAMESITE = env("AUTH_COOKIE_SAMESITE", default="None")

CORS_ALLOW_CREDENTIALS = True
```

Also widen the HMAC prefix list so the aliased v1 public route stays guarded — change `HMAC_PROTECTED_PATH_PREFIXES` default to:

```python
    default=["/api/public/", "/api/v1/public/"],
```

And add the CSRF header to allowed CORS headers (`CORS_ALLOW_HEADERS` line):

```python
CORS_ALLOW_HEADERS = (*default_headers, "x-client-id", "x-signature", "x-timestamp", "x-refresh-csrf")
```

- [ ] **Step 4: Migrate the blacklist tables**

Run: `docker compose exec backend python manage.py migrate`
Expected: applies `token_blacklist` migrations, no errors.

- [ ] **Step 5: Verify check + existing tests still pass**

Run: `docker compose exec backend python manage.py check` → "no issues".
Run: `docker compose exec backend pytest -q` → existing tests pass (public inventory unaffected).

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/config/settings.py
git commit -m "feat(auth): add simplejwt, cross-site refresh cookie + CORS credentials settings"
```

---

## Task 2: `/api/v1/` namespace + public alias

**Files:**
- Create: `backend/apps/accounts/urls.py`
- Modify: `backend/config/urls.py`

- [ ] **Step 1: Create the (initially empty) auth urlconf**

`backend/apps/accounts/urls.py`:

```python
from django.urls import path

urlpatterns: list = []  # auth routes added in Tasks 6–9
```

- [ ] **Step 2: Mount v1 + alias public**

In `config/urls.py`, replace the `api/` line with both the existing mount and the v1 mounts:

```python
    path("api/", include("apps.inventory.urls")),          # existing, unchanged
    path("api/v1/", include("apps.inventory.urls")),       # versioned alias (public routes)
    path("api/v1/auth/", include("apps.accounts.urls")),   # staff auth surface
```

- [ ] **Step 3: Verify both public paths resolve**

Run: `docker compose exec backend python manage.py shell -c "from django.urls import resolve; print(resolve('/api/v1/public/makerspaces/').view_name)"`
Expected: prints `public-makerspaces`.

- [ ] **Step 4: Commit**

```bash
git add backend/config/urls.py backend/apps/accounts/urls.py
git commit -m "feat(api): add /api/v1 namespace and alias public routes"
```

---

## Task 3: RBAC scope (`resolve_scope`, `scope_by_makerspace`)

**Files:**
- Create: `backend/apps/accounts/rbac.py`
- Test: `backend/tests/test_rbac.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_rbac.py`:

```python
import pytest
from django.contrib.auth import get_user_model

from apps.accounts import rbac
from apps.accounts.models import User
from apps.makerspaces.models import Makerspace, MakerspaceMembership

pytestmark = pytest.mark.django_db


def make_user(username, role=User.Role.REQUESTER, **kw):
    return get_user_model().objects.create_user(
        username=username, email=f"{username}@e.com", role=role, **kw
    )


def make_space(slug):
    return Makerspace.objects.create(name=slug, slug=slug)


def test_superadmin_scope_is_all():
    u = make_user("su", role=User.Role.SUPERADMIN)
    assert rbac.resolve_scope(u) is rbac.ALL


def test_admin_scope_is_membership_makerspaces():
    u = make_user("a", role=User.Role.ADMIN)
    s1, s2 = make_space("s1"), make_space("s2")
    MakerspaceMembership.objects.create(user=u, makerspace=s1)
    assert rbac.resolve_scope(u) == {s1.id}
    assert s2.id not in rbac.resolve_scope(u)


def test_requester_scope_empty():
    u = make_user("r", role=User.Role.REQUESTER)
    assert rbac.resolve_scope(u) == set()


def test_scope_by_makerspace_filters_other_tenants():
    admin = make_user("a2", role=User.Role.ADMIN)
    s1, s2 = make_space("t1"), make_space("t2")
    MakerspaceMembership.objects.create(user=admin, makerspace=s1)
    qs = Makerspace.objects.all()
    scoped = rbac.scope_by_makerspace(admin, qs, makerspace_field="id")
    assert list(scoped) == [s1]
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec backend pytest tests/test_rbac.py -q`
Expected: FAIL (`ModuleNotFoundError: apps.accounts.rbac`).

- [ ] **Step 3: Implement `rbac.py` (scope half)**

`backend/apps/accounts/rbac.py`:

```python
"""Single source of truth for role permissions + makerspace scoping (PRD §4)."""
from apps.accounts.models import User

ALL = object()  # sentinel: unrestricted (superadmin)


def resolve_scope(actor):
    """Return the set of makerspace ids the actor may act in, or ALL."""
    if actor is None or not getattr(actor, "is_authenticated", False):
        return set()
    if actor.is_superuser or actor.role == User.Role.SUPERADMIN:
        return ALL
    if actor.role in (User.Role.ADMIN, User.Role.GUEST_ADMIN):
        return set(
            actor.makerspace_memberships.values_list("makerspace_id", flat=True)
        )
    return set()


def scope_by_makerspace(actor, queryset, makerspace_field="makerspace_id"):
    """Filter a makerspace-owned queryset to the actor's scope (superadmin: unchanged)."""
    scope = resolve_scope(actor)
    if scope is ALL:
        return queryset
    if not scope:
        return queryset.none()
    return queryset.filter(**{f"{makerspace_field}__in": scope})
```

- [ ] **Step 4: Run to verify pass**

Run: `docker compose exec backend pytest tests/test_rbac.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/accounts/rbac.py backend/tests/test_rbac.py
git commit -m "feat(rbac): makerspace scope resolution + scope_by_makerspace"
```

---

## Task 4: RBAC permission matrix (`can`)

**Files:**
- Modify: `backend/apps/accounts/rbac.py`
- Modify: `backend/tests/test_rbac.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_rbac.py`:

```python
def test_can_matrix_admin_vs_guest_admin():
    admin = make_user("ad", role=User.Role.ADMIN)
    guest = make_user("gu", role=User.Role.GUEST_ADMIN)
    s = make_space("m1")
    MakerspaceMembership.objects.create(user=admin, makerspace=s, role="admin")
    MakerspaceMembership.objects.create(user=guest, makerspace=s, role="guest_admin")

    assert rbac.can(admin, rbac.Action.ACCEPT_REQUEST, s.id) is True
    assert rbac.can(guest, rbac.Action.ACCEPT_REQUEST, s.id) is False
    assert rbac.can(guest, rbac.Action.ISSUE_REQUEST, s.id) is True
    assert rbac.can(admin, rbac.Action.EDIT_INVENTORY, s.id) is True
    assert rbac.can(guest, rbac.Action.EDIT_INVENTORY, s.id) is False


def test_can_denies_out_of_scope_makerspace():
    admin = make_user("ad2", role=User.Role.ADMIN)
    s1, s2 = make_space("x1"), make_space("x2")
    MakerspaceMembership.objects.create(user=admin, makerspace=s1, role="admin")
    assert rbac.can(admin, rbac.Action.ACCEPT_REQUEST, s2.id) is False


def test_superadmin_can_everything_including_transfer():
    su = make_user("s3", role=User.Role.SUPERADMIN)
    s = make_space("z1")
    assert rbac.can(su, rbac.Action.TRANSFER_STOCK, s.id) is True
    assert rbac.can(su, rbac.Action.MANAGE_STAFF, None) is True


def test_admin_cannot_transfer_stock():
    admin = make_user("ad3", role=User.Role.ADMIN)
    s = make_space("z2")
    MakerspaceMembership.objects.create(user=admin, makerspace=s, role="admin")
    assert rbac.can(admin, rbac.Action.TRANSFER_STOCK, s.id) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec backend pytest tests/test_rbac.py -q`
Expected: FAIL (`AttributeError: module ... has no attribute 'Action'`).

- [ ] **Step 3: Implement `can` + `Action`**

Append to `apps/accounts/rbac.py`:

```python
class Action:
    VIEW_INVENTORY = "view_inventory"
    EDIT_INVENTORY = "edit_inventory"
    ACCEPT_REQUEST = "accept_request"
    REJECT_REQUEST = "reject_request"
    ASSIGN_BOX = "assign_box"
    ISSUE_REQUEST = "issue_request"
    RETURN_REQUEST = "return_request"
    MANAGE_QR = "manage_qr"
    TRANSFER_STOCK = "transfer_stock"     # superadmin only
    MANAGE_STAFF = "manage_staff"         # superadmin only
    MANAGE_MAKERSPACE = "manage_makerspace"  # superadmin only

_ADMIN_ACTIONS = {
    Action.VIEW_INVENTORY, Action.EDIT_INVENTORY, Action.ACCEPT_REQUEST,
    Action.REJECT_REQUEST, Action.ASSIGN_BOX, Action.ISSUE_REQUEST,
    Action.RETURN_REQUEST, Action.MANAGE_QR,
}
_GUEST_ADMIN_ACTIONS = {
    Action.VIEW_INVENTORY, Action.ASSIGN_BOX, Action.ISSUE_REQUEST,
}
_ROLE_ACTIONS = {
    User.Role.ADMIN: _ADMIN_ACTIONS,
    User.Role.GUEST_ADMIN: _GUEST_ADMIN_ACTIONS,
}


def can(actor, action, makerspace_id=None):
    """True if `actor` may perform `action` (optionally within `makerspace_id`)."""
    if actor is None or not getattr(actor, "is_authenticated", False):
        return False
    if actor.is_superuser or actor.role == User.Role.SUPERADMIN:
        return True
    allowed = _ROLE_ACTIONS.get(actor.role, set())
    if action not in allowed:
        return False
    if makerspace_id is None:
        return True
    scope = resolve_scope(actor)
    return scope is ALL or makerspace_id in scope
```

- [ ] **Step 4: Run to verify pass**

Run: `docker compose exec backend pytest tests/test_rbac.py -q`
Expected: PASS (all rbac tests).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/accounts/rbac.py backend/tests/test_rbac.py
git commit -m "feat(rbac): 4-role permission matrix via can()"
```

---

## Task 5: DRF permission classes + scoping mixin

**Files:**
- Create: `backend/apps/accounts/permissions.py`
- Modify: `backend/tests/test_rbac.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_rbac.py`:

```python
from rest_framework.test import APIRequestFactory

from apps.accounts.permissions import IsSuperadmin, IsStaff


def test_permission_classes_basic():
    rf = APIRequestFactory()
    su = make_user("p1", role=User.Role.SUPERADMIN)
    guest = make_user("p2", role=User.Role.GUEST_ADMIN)
    req = rf.get("/")
    req.user = su
    assert IsSuperadmin().has_permission(req, None) is True
    req.user = guest
    assert IsSuperadmin().has_permission(req, None) is False
    assert IsStaff().has_permission(req, None) is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec backend pytest tests/test_rbac.py::test_permission_classes_basic -q`
Expected: FAIL (`ModuleNotFoundError: apps.accounts.permissions`).

- [ ] **Step 3: Implement permissions + mixin**

`backend/apps/accounts/permissions.py`:

```python
"""DRF permission classes + scoping mixin built on the rbac module."""
from rest_framework.permissions import BasePermission

from apps.accounts import rbac
from apps.accounts.models import User

STAFF_ROLES = (User.Role.SUPERADMIN, User.Role.ADMIN, User.Role.GUEST_ADMIN)


def _role(request):
    u = getattr(request, "user", None)
    return getattr(u, "role", None) if getattr(u, "is_authenticated", False) else None


class IsSuperadmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(getattr(u, "is_authenticated", False)) and (
            u.is_superuser or u.role == User.Role.SUPERADMIN
        )


class IsStaff(BasePermission):
    def has_permission(self, request, view):
        return _role(request) in STAFF_ROLES


class HasMakerspaceAction(BasePermission):
    """Requires `view.required_action`; checks rbac.can within the view's makerspace.

    The view supplies the makerspace id via `get_action_makerspace_id(request)`
    (defaults to the `makerspace_id` URL kwarg)."""

    def has_permission(self, request, view):
        action = getattr(view, "required_action", None)
        if action is None:
            return False
        if hasattr(view, "get_action_makerspace_id"):
            ms_id = view.get_action_makerspace_id(request)
        else:
            ms_id = view.kwargs.get("makerspace_id")
        return rbac.can(request.user, action, ms_id)


class MakerspaceScopedQuerysetMixin:
    """Apply makerspace scoping in get_queryset so no admin view forgets it."""

    makerspace_scope_field = "makerspace_id"

    def get_queryset(self):
        qs = super().get_queryset()
        return rbac.scope_by_makerspace(
            self.request.user, qs, self.makerspace_scope_field
        )
```

- [ ] **Step 4: Run to verify pass**

Run: `docker compose exec backend pytest tests/test_rbac.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/accounts/permissions.py backend/tests/test_rbac.py
git commit -m "feat(rbac): DRF permission classes + makerspace scoping mixin"
```

---

## Task 6: Login (cookie refresh + body access) + active/access checks

**Files:**
- Create: `backend/apps/accounts/auth_cookies.py`
- Create: `backend/apps/accounts/serializers.py`
- Create: `backend/apps/accounts/views.py`
- Modify: `backend/apps/accounts/urls.py`
- Test: `backend/tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_auth.py`:

```python
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.makerspaces.models import Makerspace, MakerspaceMembership

pytestmark = pytest.mark.django_db
LOGIN = "/api/v1/auth/login"


def make_staff(username="boss", role=User.Role.ADMIN, password="pw-strong-123", **kw):
    return get_user_model().objects.create_user(
        username=username, email=f"{username}@e.com", password=password, role=role, **kw
    )


def test_login_returns_access_and_sets_refresh_cookie():
    user = make_staff()
    s = Makerspace.objects.create(name="Lab", slug="lab")
    MakerspaceMembership.objects.create(user=user, makerspace=s, role="admin")
    client = APIClient()

    resp = client.post(LOGIN, {"username": "boss", "password": "pw-strong-123"}, format="json")

    assert resp.status_code == 200
    assert "access" in resp.data
    assert "refresh" not in resp.data  # refresh lives in the cookie, never the body
    assert resp.data["user"]["role"] == "admin"
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec backend pytest tests/test_auth.py -q`
Expected: FAIL (404 — login route not wired).

- [ ] **Step 3: Implement cookie helper**

`backend/apps/accounts/auth_cookies.py`:

```python
import secrets

from django.conf import settings


def set_refresh_cookies(response, refresh_token, request=None):
    """Set the httpOnly refresh cookie + readable double-submit CSRF cookie."""
    common = {
        "secure": settings.AUTH_COOKIE_SECURE,
        "samesite": settings.AUTH_COOKIE_SAMESITE,
        "path": settings.AUTH_COOKIE_PATH,
    }
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE, str(refresh_token), httponly=True, **common
    )
    response.set_cookie(
        settings.AUTH_CSRF_COOKIE, secrets.token_urlsafe(32), httponly=False, **common
    )


def clear_refresh_cookies(response):
    for name in (settings.AUTH_REFRESH_COOKIE, settings.AUTH_CSRF_COOKIE):
        response.delete_cookie(name, path=settings.AUTH_COOKIE_PATH)
```

- [ ] **Step 4: Implement serializer + payload**

`backend/apps/accounts/serializers.py`:

```python
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts.models import User


def user_payload(user):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "is_superuser": user.is_superuser,
        "makerspaces": [
            {"id": m.makerspace_id, "slug": m.makerspace.slug, "role": m.role}
            for m in user.makerspace_memberships.select_related("makerspace")
        ],
    }


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)  # raises AuthenticationFailed on bad creds/inactive
        if self.user.access_status != User.AccessStatus.ACTIVE:
            raise AuthenticationFailed("Account access is restricted.", code="access_denied")
        data["user"] = user_payload(self.user)
        return data
```

- [ ] **Step 5: Implement the login view**

`backend/apps/accounts/views.py`:

```python
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.accounts.auth_cookies import set_refresh_cookies
from apps.accounts.serializers import LoginSerializer


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        refresh = data.pop("refresh")
        response = Response({"access": data["access"], "user": data["user"]})
        set_refresh_cookies(response, refresh, request)
        return response
```

- [ ] **Step 6: Wire the route**

`backend/apps/accounts/urls.py`:

```python
from django.urls import path

from apps.accounts.views import LoginView

urlpatterns = [
    path("login", LoginView.as_view(), name="auth-login"),
]
```

- [ ] **Step 7: Run to verify pass**

Run: `docker compose exec backend pytest tests/test_auth.py -q`
Expected: the three login tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/apps/accounts/auth_cookies.py backend/apps/accounts/serializers.py backend/apps/accounts/views.py backend/apps/accounts/urls.py backend/tests/test_auth.py
git commit -m "feat(auth): JWT login endpoint with refresh cookie + access-status gate"
```

---

## Task 7: Refresh (cookie + CSRF double-submit + rotation)

**Files:**
- Modify: `backend/apps/accounts/views.py`
- Modify: `backend/apps/accounts/urls.py`
- Modify: `backend/tests/test_auth.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_auth.py`:

```python
REFRESH = "/api/v1/auth/refresh"


def _login(client, username="boss"):
    make_staff(username=username)
    return client.post(LOGIN, {"username": username, "password": "pw-strong-123"}, format="json")


def test_refresh_requires_csrf_header():
    client = APIClient()
    _login(client)
    # cookie present from login; omit the CSRF header
    resp = client.post(REFRESH)
    assert resp.status_code == 403


def test_refresh_rotates_and_returns_new_access():
    client = APIClient()
    _login(client)
    csrf = client.cookies["refresh_csrf"].value
    resp = client.post(REFRESH, **{"HTTP_X_REFRESH_CSRF": csrf})
    assert resp.status_code == 200
    assert "access" in resp.data
    assert "refresh_token" in resp.cookies  # rotated
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec backend pytest tests/test_auth.py -k refresh -q`
Expected: FAIL (404).

- [ ] **Step 3: Implement the refresh view**

Append to `apps/accounts/views.py`:

```python
from django.conf import settings
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.auth_cookies import clear_refresh_cookies


class RefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        cookie = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE)
        if not cookie:
            raise InvalidToken("No refresh cookie.")
        csrf_cookie = request.COOKIES.get(settings.AUTH_CSRF_COOKIE)
        csrf_header = request.headers.get(settings.AUTH_CSRF_HEADER)
        if not csrf_cookie or csrf_cookie != csrf_header:
            raise PermissionDenied("Missing or invalid CSRF token.")
        serializer = self.get_serializer(data={"refresh": cookie})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(str(exc)) from exc
        data = serializer.validated_data
        response = Response({"access": data["access"]})
        new_refresh = data.get("refresh")
        if new_refresh:
            set_refresh_cookies(response, new_refresh, request)
        return response
```

- [ ] **Step 4: Wire the route**

In `apps/accounts/urls.py` import `RefreshView` and add:

```python
    path("refresh", RefreshView.as_view(), name="auth-refresh"),
```

- [ ] **Step 5: Run to verify pass**

Run: `docker compose exec backend pytest tests/test_auth.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/accounts/views.py backend/apps/accounts/urls.py backend/tests/test_auth.py
git commit -m "feat(auth): refresh endpoint with CSRF double-submit + token rotation"
```

---

## Task 8: Logout (blacklist + clear cookie)

**Files:**
- Modify: `backend/apps/accounts/views.py`, `backend/apps/accounts/urls.py`, `backend/tests/test_auth.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_auth.py`:

```python
LOGOUT = "/api/v1/auth/logout"


def test_logout_clears_cookie_and_blocks_reuse():
    client = APIClient()
    _login(client)
    old_csrf = client.cookies["refresh_csrf"].value
    out = client.post(LOGOUT)
    assert out.status_code == 200
    # cookie cleared (empty value)
    assert client.cookies["refresh_token"].value == ""
    # reusing the (now blacklisted) refresh fails — re-set cookie manually
    client.cookies["refresh_token"] = _login(APIClient()).cookies  # noqa: not reused below
```

> Implementation note for the engineer: assert the blacklisted-reuse path by capturing the refresh cookie value before logout, then POSTing to REFRESH with that value + matching csrf and asserting 401. Keep the test deterministic.

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec backend pytest tests/test_auth.py -k logout -q`
Expected: FAIL (404).

- [ ] **Step 3: Implement logout**

Append to `apps/accounts/views.py`:

```python
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        cookie = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE)
        if cookie:
            try:
                RefreshToken(cookie).blacklist()
            except TokenError:
                pass
        response = Response({"detail": "Logged out."})
        clear_refresh_cookies(response)
        return response
```

- [ ] **Step 4: Wire route + run + commit**

Add `path("logout", LogoutView.as_view(), name="auth-logout")` to urls.
Run: `docker compose exec backend pytest tests/test_auth.py -q` → PASS.

```bash
git add backend/apps/accounts/views.py backend/apps/accounts/urls.py backend/tests/test_auth.py
git commit -m "feat(auth): logout blacklists refresh token and clears cookies"
```

---

## Task 9: `/me`

**Files:**
- Modify: `backend/apps/accounts/views.py`, `backend/apps/accounts/urls.py`, `backend/tests/test_auth.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_auth.py`:

```python
ME = "/api/v1/auth/me"


def test_me_requires_auth_and_returns_profile():
    client = APIClient()
    assert client.get(ME).status_code == 401
    login = _login(client, username="meuser")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    resp = client.get(ME)
    assert resp.status_code == 200
    assert resp.data["username"] == "meuser"
    assert resp.data["role"] == "admin"
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec backend pytest tests/test_auth.py -k me -q` → FAIL (404).

- [ ] **Step 3: Implement**

Append to `apps/accounts/views.py`:

```python
from rest_framework.permissions import IsAuthenticated

from apps.accounts.serializers import user_payload


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return Response(user_payload(request.user))
```

Add `path("me", MeView.as_view(), name="auth-me")` to urls.

- [ ] **Step 4: Run + commit**

Run: `docker compose exec backend pytest tests/test_auth.py -q` → PASS.

```bash
git add backend/apps/accounts/views.py backend/apps/accounts/urls.py backend/tests/test_auth.py
git commit -m "feat(auth): /me endpoint returning role + makerspace scope"
```

---

## Task 10: OpenAPI annotations

**Files:**
- Modify: `backend/apps/accounts/views.py`

- [ ] **Step 1: Annotate** each auth view with `@extend_schema` (request/response/auth) so the spec is complete (repo convention: every endpoint documented). Add:

```python
from drf_spectacular.utils import extend_schema, OpenApiResponse
```

Annotate `LoginView.post`, `RefreshView.post`, `LogoutView.post`, `MeView.get` with request bodies and 200/401/403 responses (use inline serializers or `OpenApiResponse(description=...)`).

- [ ] **Step 2: Verify schema builds**

Run: `docker compose exec backend python manage.py spectacular --file /tmp/schema.yml`
Expected: no errors; the four `/api/v1/auth/*` paths appear.

- [ ] **Step 3: Commit**

```bash
git add backend/apps/accounts/views.py
git commit -m "docs(auth): OpenAPI annotations for auth endpoints"
```

---

## Task 11: Frontend — auth fetch client (Bearer + 401→refresh→retry)

**Files:**
- Create: `frontend/src/lib/authClient.ts`

- [ ] **Step 1: Implement the client**

`frontend/src/lib/authClient.ts`:

```typescript
import { API_URL } from "./api";

let accessToken: string | null = null;
export const setAccessToken = (t: string | null) => { accessToken = t; };
export const getAccessToken = () => accessToken;

const V1 = API_URL.replace(/\/api$/, "/api/v1");

function readCsrf(): string {
  const m = document.cookie.match(/(?:^|; )refresh_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

export async function refreshAccess(): Promise<boolean> {
  const resp = await fetch(`${V1}/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "X-Refresh-CSRF": readCsrf() },
  });
  if (!resp.ok) { setAccessToken(null); return false; }
  const data = await resp.json();
  setAccessToken(data.access);
  return true;
}

export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const doFetch = () =>
    fetch(`${V1}${path}`, {
      ...init,
      credentials: "include",
      headers: {
        ...(init.headers ?? {}),
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...(init.body ? { "Content-Type": "application/json" } : {}),
      },
    });
  let resp = await doFetch();
  if (resp.status === 401 && (await refreshAccess())) {
    resp = await doFetch();
  }
  return resp;
}
```

- [ ] **Step 2: Build check**

Run: `cd frontend && npm run build`
Expected: type-checks and builds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/authClient.ts
git commit -m "feat(auth-fe): bearer fetch wrapper with silent refresh retry"
```

---

## Task 12: Frontend — AuthContext + provider

**Files:**
- Create: `frontend/src/features/auth/authApi.ts`
- Create: `frontend/src/features/auth/AuthContext.tsx`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: API calls**

`frontend/src/features/auth/authApi.ts`:

```typescript
import { API_URL } from "../../lib/api";
import { authFetch, setAccessToken } from "../../lib/authClient";

const V1 = API_URL.replace(/\/api$/, "/api/v1");

export type Membership = { id: number; slug: string; role: string };
export type AuthUser = {
  id: number; username: string; email: string;
  role: string; is_superuser: boolean; makerspaces: Membership[];
};

export async function login(username: string, password: string): Promise<AuthUser> {
  const resp = await fetch(`${V1}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!resp.ok) throw new Error("Invalid credentials");
  const data = await resp.json();
  setAccessToken(data.access);
  return data.user as AuthUser;
}

export async function fetchMe(): Promise<AuthUser | null> {
  const resp = await authFetch("/auth/me");
  return resp.ok ? ((await resp.json()) as AuthUser) : null;
}

export async function logout(): Promise<void> {
  await fetch(`${V1}/auth/logout`, { method: "POST", credentials: "include" });
  setAccessToken(null);
}
```

`frontend/src/features/auth/AuthContext.tsx`:

```tsx
import { createContext, useContext, useEffect, useState, ReactNode } from "react";

import { refreshAccess } from "../../lib/authClient";
import { AuthUser, fetchMe, login as apiLogin, logout as apiLogout } from "./authApi";

type AuthState = {
  user: AuthUser | null;
  loading: boolean;
  login: (u: string, p: string) => Promise<void>;
  logout: () => Promise<void>;
};

const Ctx = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Silent refresh on load: cookie -> access token -> /me.
    (async () => {
      if (await refreshAccess()) setUser(await fetchMe());
      setLoading(false);
    })();
  }, []);

  const value: AuthState = {
    user,
    loading,
    login: async (u, p) => setUser(await apiLogin(u, p)),
    logout: async () => { await apiLogout(); setUser(null); },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
```

- [ ] **Step 2: Wrap the app**

In `frontend/src/main.tsx`, import `AuthProvider` and wrap `<App />` inside `<BrowserRouter>`:

```tsx
import { AuthProvider } from "./features/auth/AuthContext";
// ...
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
```

- [ ] **Step 3: Build + commit**

Run: `cd frontend && npm run build` → builds.

```bash
git add frontend/src/features/auth/authApi.ts frontend/src/features/auth/AuthContext.tsx frontend/src/main.tsx
git commit -m "feat(auth-fe): auth context with silent refresh on load"
```

---

## Task 13: Frontend — Login page + protected route

**Files:**
- Create: `frontend/src/features/auth/LoginPage.tsx`
- Create: `frontend/src/features/auth/RequireAuth.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Login page**

`frontend/src/features/auth/LoginPage.tsx`:

```tsx
import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "./AuthContext";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await login(username, password);
      navigate("/admin");
    } catch {
      setError("Invalid username or password.");
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-bg px-6">
      <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4 rounded-lg border border-line bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-bold text-ink">Staff sign in</h1>
        {error ? <p className="text-sm text-danger">{error}</p> : null}
        <input className="w-full rounded border border-line p-2" placeholder="Username"
          value={username} onChange={(e) => setUsername(e.target.value)} />
        <input type="password" className="w-full rounded border border-line p-2" placeholder="Password"
          value={password} onChange={(e) => setPassword(e.target.value)} />
        <button type="submit" className="w-full rounded bg-tinker py-2 font-semibold text-ink">Sign in</button>
      </form>
    </main>
  );
}
```

- [ ] **Step 2: RequireAuth wrapper**

`frontend/src/features/auth/RequireAuth.tsx`:

```tsx
import { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { Spinner } from "../../components/ui/Spinner";
import { useAuth } from "./AuthContext";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="grid min-h-screen place-items-center"><Spinner /></div>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
```

- [ ] **Step 3: Routes**

In `frontend/src/App.tsx`, import and add routes. Add a minimal placeholder admin landing that proves auth works:

```tsx
import { LoginPage } from "./features/auth/LoginPage";
import { RequireAuth } from "./features/auth/RequireAuth";
import { useAuth } from "./features/auth/AuthContext";

function AdminHome() {
  const { user, logout } = useAuth();
  return (
    <main className="min-h-screen bg-bg p-8">
      <h1 className="text-3xl font-bold text-ink">Signed in as {user?.username}</h1>
      <p className="mt-2 text-ink/70">Role: {user?.role}</p>
      <button onClick={() => logout()} className="mt-4 rounded bg-ink px-4 py-2 text-white">Sign out</button>
    </main>
  );
}
```

Add inside `<Routes>`:

```tsx
      <Route path="/login" element={<LoginPage />} />
      <Route path="/admin" element={<RequireAuth><AdminHome /></RequireAuth>} />
```

- [ ] **Step 4: Build + commit**

Run: `cd frontend && npm run build` → builds.

```bash
git add frontend/src/features/auth/LoginPage.tsx frontend/src/features/auth/RequireAuth.tsx frontend/src/App.tsx
git commit -m "feat(auth-fe): login page + protected /admin route"
```

---

## Task 14: Full backend suite + manual smoke

- [ ] **Step 1:** `docker compose exec backend pytest -q` → all pass.
- [ ] **Step 2:** `docker compose exec backend python manage.py check` → no issues.
- [ ] **Step 3:** Manual: create an admin user in Django admin, assign a makerspace membership, `POST /api/v1/auth/login`, confirm access token + refresh cookie, then `GET /api/v1/auth/me` with Bearer → profile with makerspace scope.
- [ ] **Step 4:** Update `CLAUDE.md` (Project Status + conventions): note `/api/v1/` versioning, the auth endpoints, the RBAC module as the scoping authority, and that ApiClient/HMAC-registry is deferred to Phase 10.

```bash
git add CLAUDE.md
git commit -m "docs: record Phase 2 auth/RBAC + /api/v1 conventions"
```

---

## Self-Review Notes (coverage vs spec)

- Spec §2 token model → Tasks 1, 6, 7 (lifetimes, cookie attrs, rotation, CSRF). ✓
- Spec §4 endpoints → Tasks 6–9 (login/refresh/logout/me) + Task 10 OpenAPI. ✓
- Spec §5 RBAC (`can`, `scope_by_makerspace`, permission classes, mixin) → Tasks 3–5. ✓
- Spec §6 settings/CORS → Task 1. ✓
- Spec §7 frontend shell → Tasks 11–13 (in-memory token, silent refresh, 401-retry, /me gate). ✓
- Spec §9 tests (role matrix, cross-tenant denial, suspended, rotation, CSRF) → Tasks 3–9. ✓
- Spec §10 docs → Task 14. ✓
- ApiClient registry intentionally absent (deferred to Phase 10 per scope decision). ✓
