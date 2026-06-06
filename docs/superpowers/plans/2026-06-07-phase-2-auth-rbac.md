# Phase 2 — Auth + RBAC + Makerspace Scoping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In THIS repo, Stage-2 implementation is delegated to Codex per `~/.claude/CLAUDE.md`; Claude verifies each task group.

**Goal:** Staff (superadmin/admin/guest-admin) can log into a separate-origin frontend via JWT, and every staff query is permission-checked and scoped to assigned makerspaces.

**Architecture:** `djangorestframework-simplejwt` issues a short-lived access token (returned in the JSON body, held in browser memory) and a long-lived refresh token (set as a cross-site `HttpOnly; Secure; SameSite=None`, `max_age`-bounded cookie scoped to the refresh path). The refresh and logout endpoints are CSRF-defended by requiring a custom header (forces a CORS preflight an attacker origin can't pass) plus an explicit Origin-allowlist check — the cross-origin-correct alternative to an unreadable double-submit cookie. A single RBAC module (`apps/accounts/rbac.py`) owns the 4-role permission matrix (keyed on per-makerspace `MakerspaceMembership.role`) and `scope_by_makerspace`; DRF defaults to deny-by-default with a `StaffAPIView` base that auto-scopes querysets. New surface mounts under `/api/v1/`; existing public routes are aliased there without breaking.

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
    # DENY BY DEFAULT (review fix #4): every view requires auth unless it explicitly
    # opts into AllowAny. Public views are marked AllowAny in Step 3b.
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
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
# CSRF defense for the cookie-bearing endpoints (refresh/logout): the view requires
# this custom header to be PRESENT — a non-simple header forces a CORS preflight that
# an attacker's origin cannot pass — AND validates the Origin header against the
# allowlist (review fixes #1, #8). The header VALUE is not a secret; presence + Origin
# is the defense. This works cross-origin where a readable double-submit cookie cannot.
AUTH_REFRESH_CSRF_HEADER = "X-Refresh-CSRF"
AUTH_COOKIE_PATH = "/api/v1/auth/"
# SameSite=None REQUIRES Secure or browsers silently drop the cookie (review fix #2).
# Prod (separate origins over HTTPS): SAMESITE=None, SECURE=True.
# Local dev: serve the frontend through a same-origin Vite proxy to the API and set
# AUTH_COOKIE_SAMESITE=Lax + AUTH_COOKIE_SECURE=False via .env (see Step 3c note).
AUTH_COOKIE_SAMESITE = env("AUTH_COOKIE_SAMESITE", default="None")
AUTH_COOKIE_SECURE = env.bool("AUTH_COOKIE_SECURE", default=True)

CORS_ALLOW_CREDENTIALS = True
```

Also widen the HMAC prefix list so the aliased v1 public route stays guarded — change `HMAC_PROTECTED_PATH_PREFIXES` default to:

```python
    default=["/api/public/", "/api/v1/public/"],
```

> **Deployment note (review fix #9):** any environment that sets `HMAC_PROTECTED_PATH_PREFIXES` explicitly will NOT pick up this new default. Update `.env.example` and document that deployments must add `/api/v1/public/` to the env value, or the aliased v1 public route will be unguarded. Task 14 smoke-tests both `/api/public/...` and `/api/v1/public/...`.

And add the CSRF header to allowed CORS headers (`CORS_ALLOW_HEADERS` line):

```python
CORS_ALLOW_HEADERS = (*default_headers, "x-client-id", "x-signature", "x-timestamp", "x-refresh-csrf")
```

- [ ] **Step 3b: Keep public endpoints open under deny-by-default (review fix #4)**

Because the default is now `IsAuthenticated`, the existing public views MUST opt into
`AllowAny` or the public inventory flow breaks. In `backend/apps/inventory/views.py`, add
the import and set `permission_classes` on both views:

```python
from rest_framework.permissions import AllowAny
# ...
class PublicMakerspaceListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicMakerspaceSerializer
    # ... unchanged ...

class PublicInventoryListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicProductSerializer
    # ... unchanged ...
```

The existing public-inventory tests (`tests/test_public_inventory.py`) are the regression
guard — they must still pass in Step 5.

- [ ] **Step 3c: Document the local-dev cookie strategy (review fix #2)**

Add to `backend/.env.example` (and note in CLAUDE.md):

```
# Production (separate HTTPS origins): leave defaults (SameSite=None, Secure=True).
# Local dev: serve the frontend via a same-origin Vite proxy to :8000 and set:
# AUTH_COOKIE_SAMESITE=Lax
# AUTH_COOKIE_SECURE=False
AUTH_COOKIE_SAMESITE=None
AUTH_COOKIE_SECURE=True
```

In `frontend/vite.config.ts`, add a dev proxy so the browser talks to the frontend origin
only (making the refresh cookie first-party in dev):

```typescript
server: {
  port: 5000,
  proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true } },
},
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


def test_membership_role_overrides_global_role():
    # Globally `admin`, but only a guest_admin member of THIS makerspace.
    u = make_user("mix", role=User.Role.ADMIN)
    s = make_space("mx")
    MakerspaceMembership.objects.create(user=u, makerspace=s, role="guest_admin")
    assert rbac.can(u, rbac.Action.ACCEPT_REQUEST, s.id) is False  # guest can't accept
    assert rbac.can(u, rbac.Action.ISSUE_REQUEST, s.id) is True    # guest can issue


def test_non_member_denied_even_with_global_staff_role():
    u = make_user("nm", role=User.Role.ADMIN)
    s = make_space("nm1")  # no membership created
    assert rbac.can(u, rbac.Action.VIEW_INVENTORY, s.id) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec backend pytest tests/test_rbac.py -q`
Expected: FAIL (`AttributeError: module ... has no attribute 'Action'`).

- [ ] **Step 3: Implement `can` + `Action`**

Append to `apps/accounts/rbac.py`:

Add the import for `MakerspaceMembership` at the top of `rbac.py`:

```python
from apps.makerspaces.models import MakerspaceMembership
```

Then append:

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
    TRANSFER_STOCK = "transfer_stock"        # superadmin only
    MANAGE_STAFF = "manage_staff"            # superadmin only
    MANAGE_MAKERSPACE = "manage_makerspace"  # superadmin only

_ADMIN_ACTIONS = {
    Action.VIEW_INVENTORY, Action.EDIT_INVENTORY, Action.ACCEPT_REQUEST,
    Action.REJECT_REQUEST, Action.ASSIGN_BOX, Action.ISSUE_REQUEST,
    Action.RETURN_REQUEST, Action.MANAGE_QR,
}
_GUEST_ADMIN_ACTIONS = {
    Action.VIEW_INVENTORY, Action.ASSIGN_BOX, Action.ISSUE_REQUEST,
}
# Authority for non-superadmins is keyed on the PER-MAKERSPACE membership role,
# NOT the global User.role (review fix #3). A user who is globally `admin` but only a
# guest_admin member of makerspace B gets only guest_admin actions in B.
_MEMBERSHIP_ROLE_ACTIONS = {
    MakerspaceMembership.Role.ADMIN: _ADMIN_ACTIONS,
    MakerspaceMembership.Role.GUEST_ADMIN: _GUEST_ADMIN_ACTIONS,
}


def membership_role(actor, makerspace_id):
    """Return the actor's MakerspaceMembership.role for this makerspace, or None."""
    membership = actor.makerspace_memberships.filter(
        makerspace_id=makerspace_id
    ).first()
    return membership.role if membership else None


def can(actor, action, makerspace_id=None):
    """True if `actor` may perform `action` within `makerspace_id`.

    Superadmin: everything. Everyone else: authority is per-makerspace, so a
    makerspace_id is required and the membership role decides the allowed actions."""
    if actor is None or not getattr(actor, "is_authenticated", False):
        return False
    if actor.is_superuser or actor.role == User.Role.SUPERADMIN:
        return True
    if makerspace_id is None:
        return False
    role = membership_role(actor, makerspace_id)
    if role is None:
        return False
    return action in _MEMBERSHIP_ROLE_ACTIONS.get(role, set())
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


def test_isstaff_rejects_suspended_after_login():
    rf = APIRequestFactory()
    suspended = make_user("p3", role=User.Role.ADMIN,
                          access_status=User.AccessStatus.SUSPENDED)
    req = rf.get("/")
    req.user = suspended
    assert IsStaff().has_permission(req, None) is False


def test_issuperadmin_rejects_suspended_superadmin():
    rf = APIRequestFactory()
    su = make_user("p4", role=User.Role.SUPERADMIN,
                   access_status=User.AccessStatus.SUSPENDED)
    req = rf.get("/")
    req.user = su
    assert IsSuperadmin().has_permission(req, None) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec backend pytest tests/test_rbac.py::test_permission_classes_basic -q`
Expected: FAIL (`ModuleNotFoundError: apps.accounts.permissions`).

- [ ] **Step 3: Implement permissions + mixin**

`backend/apps/accounts/permissions.py`:

```python
"""DRF permission classes + scoping mixin + staff base view built on the rbac module."""
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import BasePermission, IsAuthenticated

from apps.accounts import rbac
from apps.accounts.models import User

STAFF_ROLES = (User.Role.SUPERADMIN, User.Role.ADMIN, User.Role.GUEST_ADMIN)


def _active_staff(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and user.role in STAFF_ROLES
        and user.access_status == User.AccessStatus.ACTIVE
    )


class IsSuperadmin(BasePermission):
    def has_permission(self, request, view):
        u = getattr(request, "user", None)
        if not getattr(u, "is_authenticated", False):
            return False
        # re-review fix: a suspended/restricted superadmin must also be blocked.
        if u.access_status != User.AccessStatus.ACTIVE:
            return False
        return u.is_superuser or u.role == User.Role.SUPERADMIN


class IsStaff(BasePermission):
    """Authenticated staff whose access_status is still ACTIVE.

    Re-checking access_status here — not only at login — bounds a suspended user's
    remaining access to the (short) access-token lifetime (review fix #5)."""

    def has_permission(self, request, view):
        return _active_staff(getattr(request, "user", None))


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


class StaffAPIView(MakerspaceScopedQuerysetMixin, GenericAPIView):
    """Base for ALL staff endpoints: authenticated + active staff + auto-scoped queryset.

    Future phases subclass this so the invariant 'every staff query is makerspace-scoped'
    is enforced by default rather than by remembering to add a mixin (review fix #4). Add
    `required_action` + `HasMakerspaceAction` to a subclass for per-action checks."""

    permission_classes = [IsAuthenticated, IsStaff]
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
from urllib.parse import urlsplit

from django.conf import settings
from rest_framework.exceptions import PermissionDenied


def _refresh_max_age():
    return int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())


def set_refresh_cookies(response, refresh_token, request=None):
    """Set the long-lived httpOnly refresh cookie.

    Explicit max_age (review fix #7) — without it the cookie would be a session cookie
    and die on browser close, despite the 7-day token lifetime."""
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE,
        str(refresh_token),
        max_age=_refresh_max_age(),
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path=settings.AUTH_COOKIE_PATH,
    )


def clear_refresh_cookies(response):
    response.delete_cookie(settings.AUTH_REFRESH_COOKIE, path=settings.AUTH_COOKIE_PATH)


def _origin_allowed(raw):
    """Exact scheme://host[:port] match against the allowlist (no prefix bypass).

    re-review fix: `startswith` accepted `http://localhost:5000.evil.test`. Parse the
    Origin/Referer and compare the exact scheme+netloc."""
    if not raw:
        return False
    parts = urlsplit(raw)
    if not parts.scheme or not parts.netloc:
        return False
    candidate = f"{parts.scheme}://{parts.netloc}"
    return candidate in set(settings.CORS_ALLOWED_ORIGINS)


def assert_csrf(request):
    """CSRF guard for cookie-bearing endpoints — refresh & logout (review fixes #1, #8).

    Requires the custom header to be PRESENT (a non-simple header forces a CORS preflight
    that an attacker origin cannot pass) AND the Origin/Referer to exactly match an
    allowlisted origin. No readable cookie is needed, so this works across separate origins."""
    if settings.AUTH_REFRESH_CSRF_HEADER not in request.headers:
        raise PermissionDenied("Missing CSRF header.")
    origin = request.headers.get("Origin") or request.headers.get("Referer", "")
    if not _origin_allowed(origin):
        raise PermissionDenied("Origin not allowed.")
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
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.accounts.auth_cookies import set_refresh_cookies
from apps.accounts.serializers import LoginSerializer


class LoginView(TokenObtainPairView):
    # Explicit under deny-by-default (DEFAULT_PERMISSION_CLASSES=IsAuthenticated):
    # obtaining a token must be open. RefreshView inherits simplejwt's AllowAny.
    permission_classes = [AllowAny]
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
    # Replay the OLD token — blacklist-after-rotation must reject it (review fix #6).
    replay = APIClient()
    replay.cookies["refresh_token"] = old_refresh
    resp = replay.post(REFRESH, **_csrf_headers())
    assert resp.status_code == 401
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec backend pytest tests/test_auth.py -k refresh -q`
Expected: FAIL (404).

- [ ] **Step 3: Implement the refresh view**

Append to `apps/accounts/views.py` (merge the new imports with the ones already at the
top of the file from Task 6):

```python
from django.conf import settings
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.auth_cookies import assert_csrf, clear_refresh_cookies
from apps.accounts.models import User


def _refresh_user_is_active(token_str):
    """Return False if the refresh token's user is suspended/restricted/inactive."""
    try:
        token = RefreshToken(token_str)
    except TokenError:
        return True  # invalid token: let the serializer reject it as 401, not 403
    user = User.objects.filter(pk=token.get("user_id")).first()
    return bool(
        user and user.is_active and user.access_status == User.AccessStatus.ACTIVE
    )


class RefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        assert_csrf(request)  # header presence + Origin allowlist (CSRF defense)
        cookie = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE)
        if not cookie:
            raise InvalidToken("No refresh cookie.")
        if not _refresh_user_is_active(cookie):  # review fix #5
            response = Response({"detail": "Account access is restricted."}, status=403)
            clear_refresh_cookies(response)
            return response
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec backend pytest tests/test_auth.py -k logout -q`
Expected: FAIL (404).

- [ ] **Step 3: Implement logout**

Append to `apps/accounts/views.py`:

```python
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

# RefreshToken, TokenError, assert_csrf, clear_refresh_cookies already imported (Task 7).


class LogoutView(APIView):
    permission_classes = [AllowAny]  # cookie-based; protected by assert_csrf below

    def post(self, request, *args, **kwargs):
        assert_csrf(request)  # review fix #8: logout must not be CSRF-able
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

// CSRF header for cookie endpoints. The VALUE is not a secret — its presence forces a
// CORS preflight, and the server also checks Origin against its allowlist. Export so
// logout reuses it.
export const CSRF_HEADER = { "X-Refresh-CSRF": "1" };

export async function refreshAccess(): Promise<boolean> {
  const resp = await fetch(`${V1}/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { ...CSRF_HEADER },
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
import { authFetch, CSRF_HEADER, setAccessToken } from "../../lib/authClient";

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
  await fetch(`${V1}/auth/logout`, {
    method: "POST",
    credentials: "include",
    headers: { ...CSRF_HEADER },
  });
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

## Task 14: `ApiClient` model + encrypted secret (new app `apps/apiclients/`)

**Files:**
- Modify: `backend/requirements.txt` (add `cryptography`), `backend/config/settings.py`
- Create: `backend/apps/apiclients/__init__.py`, `apps.py`, `crypto.py`, `models.py`
- Test: `backend/tests/test_apiclients.py`

- [ ] **Step 1: Dependency + settings**

Add to `requirements.txt`: `cryptography>=42`. In `settings.py` add `"apps.apiclients",`
to `INSTALLED_APPS` and:

```python
# Fernet key for encrypting ApiClient secrets at rest. Generate with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# default="" (review fix #5) so settings import never fails when encryption isn't used;
# _fernet() raises ImproperlyConfigured only when a key is actually needed. Tests/CI get a
# real key from .env / docker-compose (added below).
API_CLIENT_ENC_KEY = env("API_CLIENT_ENC_KEY", default="")
# When True, requests to HMAC_PROTECTED_PATH_PREFIXES must carry a valid signed client.
API_CLIENT_AUTH_REQUIRED = env.bool("API_CLIENT_AUTH_REQUIRED", default=False)
```

Add `API_CLIENT_ENC_KEY` to `backend/.env`, `backend/.env.example`, and the backend
service `environment:` in `docker-compose.yml` (tests load `config.settings`, so the key
must be present in the test env too).

- [ ] **Step 2: App config + crypto helper**

`apps/apiclients/apps.py`:

```python
from django.apps import AppConfig


class ApiClientsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.apiclients"
```

`apps/apiclients/crypto.py`:

```python
from cryptography.fernet import Fernet
from django.conf import settings


def _fernet():
    if not settings.API_CLIENT_ENC_KEY:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(
            "API_CLIENT_ENC_KEY must be set to encrypt/decrypt ApiClient secrets."
        )
    return Fernet(settings.API_CLIENT_ENC_KEY.encode())


def encrypt_secret(raw):
    return _fernet().encrypt(raw.encode())


def decrypt_secret(token):
    return _fernet().decrypt(bytes(token)).decode()
```

- [ ] **Step 3: Write the failing test**

`backend/tests/test_apiclients.py`:

```python
import pytest

from apps.apiclients.models import ApiClient
from apps.makerspaces.models import Makerspace

pytestmark = pytest.mark.django_db


def test_issue_returns_raw_secret_and_stores_it_encrypted():
    s = Makerspace.objects.create(name="Kochi", slug="kochi")
    client, raw = ApiClient.issue(
        label="Kochi public", makerspace=s, allowed_origins=["http://localhost:5000"]
    )
    assert client.client_id.startswith("ck_")
    assert client.get_secret() == raw                 # round-trips
    assert bytes(client.secret_encrypted) != raw.encode()  # NOT plaintext at rest
```

- [ ] **Step 4: Run to verify it fails**

Run: `docker compose exec backend pytest tests/test_apiclients.py -q`
Expected: FAIL (`ModuleNotFoundError: apps.apiclients.models`).

- [ ] **Step 5: Implement the model**

`apps/apiclients/models.py`:

```python
import secrets

from django.conf import settings
from django.db import models

from apps.apiclients.crypto import decrypt_secret, encrypt_secret
from apps.makerspaces.models import Makerspace


def generate_client_id():
    return f"ck_{secrets.token_urlsafe(18)}"


class ApiClient(models.Model):
    """A signed API client (client_id + HMAC secret) scoped to a makerspace.

    Secret is stored ENCRYPTED (Fernet), not hashed — HMAC verification needs the raw
    secret back. `makerspace=None` is a global client (superadmin only)."""

    label = models.CharField(max_length=200)
    client_id = models.CharField(
        max_length=64, unique=True, default=generate_client_id, editable=False
    )
    secret_encrypted = models.BinaryField(editable=False)
    makerspace = models.ForeignKey(
        Makerspace, null=True, blank=True, on_delete=models.CASCADE,
        related_name="api_clients",
    )
    allowed_origins = models.JSONField(default=list, blank=True)  # exact scheme://host[:port]
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="created_api_clients",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_secret(self, raw):
        self.secret_encrypted = encrypt_secret(raw)

    def get_secret(self):
        return decrypt_secret(self.secret_encrypted)

    def clean(self):
        # review fix #4: an HMAC client must restrict to at least one exact origin.
        from django.core.exceptions import ValidationError

        if not self.allowed_origins:
            raise ValidationError(
                {"allowed_origins": "At least one allowed origin is required."}
            )

    @classmethod
    def issue(cls, *, label, makerspace=None, allowed_origins=None, created_by=None):
        raw = secrets.token_urlsafe(32)
        obj = cls(
            label=label, makerspace=makerspace,
            allowed_origins=allowed_origins or [], created_by=created_by,
        )
        obj.set_secret(raw)
        obj.save()
        return obj, raw  # raw secret shown to the operator exactly once

    def __str__(self):
        return f"{self.label} ({self.client_id})"
```

- [ ] **Step 6: Migrate + test + commit**

```bash
docker compose exec backend python manage.py makemigrations apiclients
docker compose exec backend python manage.py migrate
docker compose exec backend pytest tests/test_apiclients.py -q   # PASS
git add backend/requirements.txt backend/config/settings.py backend/apps/apiclients backend/tests/test_apiclients.py backend/.env.example docker-compose.yml
git commit -m "feat(apiclients): ApiClient model with Fernet-encrypted secret"
```

---

## Task 15: Themed admin for ApiClient (superadmin + scoped admin)

**Files:**
- Create: `backend/apps/apiclients/admin.py`
- Modify: `backend/config/unfold.py` (sidebar entry)
- Test: `backend/tests/test_apiclients.py`

- [ ] **Step 1: Add failing scoping test**

Append to `tests/test_apiclients.py`:

```python
from django.contrib.auth import get_user_model

from apps.accounts.models import User
from apps.apiclients.admin import ApiClientAdmin
from apps.makerspaces.models import MakerspaceMembership
from django.contrib.admin.sites import AdminSite
from rest_framework.test import APIRequestFactory


def _admin_user(username, role=User.Role.ADMIN):
    return get_user_model().objects.create_user(
        username=username, email=f"{username}@e.com", role=role
    )


def test_admin_changelist_scoped_to_own_makerspace():
    a, b = Makerspace.objects.create(name="A", slug="a"), Makerspace.objects.create(name="B", slug="b")
    ApiClient.issue(label="A-client", makerspace=a)
    ApiClient.issue(label="B-client", makerspace=b)
    admin_user = _admin_user("scoped")
    MakerspaceMembership.objects.create(user=admin_user, makerspace=a, role="admin")

    req = APIRequestFactory().get("/")
    req.user = admin_user
    qs = ApiClientAdmin(ApiClient, AdminSite()).get_queryset(req)
    assert {c.makerspace_id for c in qs} == {a.id}  # cannot see B's client
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec backend pytest tests/test_apiclients.py::test_admin_changelist_scoped_to_own_makerspace -q`
Expected: FAIL (`ModuleNotFoundError: apps.apiclients.admin`).

- [ ] **Step 3: Implement the admin**

`apps/apiclients/admin.py`:

```python
import secrets

from django.contrib import admin, messages
from unfold.admin import ModelAdmin

from apps.accounts import rbac
from apps.accounts.models import User
from apps.apiclients.models import ApiClient
from apps.makerspaces.models import Makerspace

MANAGER_ROLES = (User.Role.SUPERADMIN, User.Role.ADMIN)


def _is_superadmin(user):
    return user.is_superuser or user.role == User.Role.SUPERADMIN


@admin.register(ApiClient)
class ApiClientAdmin(ModelAdmin):
    list_display = ("label", "client_id", "makerspace", "is_active", "created_at")
    list_filter = ("is_active", "makerspace")
    readonly_fields = ("client_id", "created_by", "created_at", "updated_at")
    fields = (
        "label", "makerspace", "allowed_origins", "is_active",
        "client_id", "created_by", "created_at", "updated_at",
    )

    # Only ACTIVE superadmin + makerspace admins reach this admin at all
    # (review fixes #1 correct signatures, #2 access_status).
    def has_module_permission(self, request):
        u = getattr(request, "user", None)
        return bool(
            u and u.is_authenticated and u.is_active
            and u.access_status == User.AccessStatus.ACTIVE
            and (u.is_superuser or u.role in MANAGER_ROLES)
        )

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)

    # Admins see/edit only clients in their assigned makerspaces (superadmin: all).
    def get_queryset(self, request):
        return rbac.scope_by_makerspace(
            request.user, super().get_queryset(request), "makerspace_id"
        )

    # Admins can only target their own makerspaces and MUST pick one (no global client).
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "makerspace" and not _is_superadmin(request.user):
            scope = rbac.resolve_scope(request.user)
            ids = [] if scope is rbac.ALL else scope
            kwargs["queryset"] = Makerspace.objects.filter(id__in=ids)
            kwargs["required"] = True
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    # Generate + reveal the secret once at creation.
    def save_model(self, request, obj, form, change):
        new_secret = None
        if not change:
            obj.created_by = request.user
            new_secret = secrets.token_urlsafe(32)
            obj.set_secret(new_secret)
        super().save_model(request, obj, form, change)
        if new_secret:
            messages.warning(
                request,
                f"Client secret for {obj.client_id} (shown once — copy it now): {new_secret}",
            )
```

- [ ] **Step 4: Sidebar entry**

In `config/unfold.py`, add a `_can_view_api_clients(request)` predicate (superadmin or
admin role) and an "API Clients" item under a sensible section linking to
`admin:apiclients_apiclient_changelist`.

- [ ] **Step 5: Run + commit**

```bash
docker compose exec backend pytest tests/test_apiclients.py -q   # PASS
docker compose exec backend python manage.py check               # no issues
git add backend/apps/apiclients/admin.py backend/config/unfold.py backend/tests/test_apiclients.py
git commit -m "feat(apiclients): scoped Unfold admin, secret shown once"
```

---

## Task 16: Upgrade `FrontendHMACMiddleware` to multi-client DB lookup

**Files:**
- Modify: `backend/apps/inventory/middleware.py`
- Test: `backend/tests/test_apiclients.py`

- [ ] **Step 1: Add failing middleware tests**

Append to `tests/test_apiclients.py`:

```python
import hashlib
import hmac
import time

from django.test import override_settings
from rest_framework.test import APIClient

PUBLIC = "/api/v1/public/makerspaces/"


def _sign(client_obj, raw_secret, path, origin):
    ts = str(int(time.time()))
    msg = b"\n".join([b"GET", path.encode(), ts.encode(), b""])
    sig = hmac.new(raw_secret.encode(), msg, hashlib.sha256).hexdigest()
    return {
        "HTTP_X_CLIENT_ID": client_obj.client_id,
        "HTTP_X_TIMESTAMP": ts,
        "HTTP_X_SIGNATURE": sig,
        "HTTP_ORIGIN": origin,
    }


@override_settings(API_CLIENT_AUTH_REQUIRED=True)
def test_valid_signed_client_passes():
    obj, raw = ApiClient.issue(label="ok", allowed_origins=["http://localhost:5000"])
    resp = APIClient().get(PUBLIC, **_sign(obj, raw, PUBLIC, "http://localhost:5000"))
    assert resp.status_code == 200


@override_settings(API_CLIENT_AUTH_REQUIRED=True)
def test_unknown_client_rejected():
    resp = APIClient().get(PUBLIC, HTTP_X_CLIENT_ID="ck_nope", HTTP_X_TIMESTAMP="1",
                           HTTP_X_SIGNATURE="x", HTTP_ORIGIN="http://localhost:5000")
    assert resp.status_code == 401


@override_settings(API_CLIENT_AUTH_REQUIRED=True)
def test_disallowed_origin_rejected():
    obj, raw = ApiClient.issue(label="ok2", allowed_origins=["http://localhost:5000"])
    resp = APIClient().get(PUBLIC, **_sign(obj, raw, PUBLIC, "https://evil.test"))
    assert resp.status_code == 401


@override_settings(API_CLIENT_AUTH_REQUIRED=True)
def test_inactive_client_rejected():
    obj, raw = ApiClient.issue(label="off", allowed_origins=["http://localhost:5000"])
    obj.is_active = False
    obj.save()
    resp = APIClient().get(PUBLIC, **_sign(obj, raw, PUBLIC, "http://localhost:5000"))
    assert resp.status_code == 401


def test_auth_not_required_lets_public_through():
    # Default API_CLIENT_AUTH_REQUIRED=False → unsigned public request still works.
    Makerspace.objects.create(name="Open", slug="open", public_inventory_enabled=True)
    assert APIClient().get(PUBLIC).status_code == 200
```

- [ ] **Step 2: Run to verify failures**

Run: `docker compose exec backend pytest tests/test_apiclients.py -k "client or origin or public" -q`
Expected: signed/unknown/origin/inactive tests FAIL (middleware still uses single env client).

- [ ] **Step 3: Rewrite the middleware**

Replace the body of `apps/inventory/middleware.py` so validation is DB-driven and
**fails safe** (any error → deny):

```python
import hashlib
import hmac
import logging
import time
from urllib.parse import urlsplit

from django.conf import settings
from django.http import JsonResponse

logger = logging.getLogger(__name__)


class FrontendHMACMiddleware:
    """Validate signed client requests for protected API paths using the ApiClient registry."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._should_validate(request) and not self._is_valid(request):
            return JsonResponse({"detail": "Invalid client signature."}, status=401)
        return self.get_response(request)

    def _should_validate(self, request):
        if request.method == "OPTIONS" or not settings.API_CLIENT_AUTH_REQUIRED:
            return False
        return any(
            request.path.startswith(p) for p in settings.HMAC_PROTECTED_PATH_PREFIXES
        )

    def _is_valid(self, request):
        try:
            from apps.apiclients.models import ApiClient

            client_id = request.headers.get("X-Client-Id", "")
            timestamp = request.headers.get("X-Timestamp", "")
            signature = request.headers.get("X-Signature", "")
            if not (client_id and timestamp and signature):
                return False

            client = ApiClient.objects.filter(
                client_id=client_id, is_active=True
            ).first()
            if client is None:
                return False

            if not self._origin_ok(request, client):
                return False

            try:
                skew = abs(int(time.time()) - int(timestamp))
            except ValueError:
                return False
            if skew > settings.HMAC_MAX_CLOCK_SKEW_SECONDS:
                return False

            message = b"\n".join([
                request.method.upper().encode(),
                request.get_full_path().encode(),
                timestamp.encode(),
                request.body,
            ])
            expected = hmac.new(
                client.get_secret().encode(), message, hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(signature, expected)
        except Exception:  # fail safe — never 500 the request flow
            logger.exception("ApiClient signature validation failed")
            return False

    def _origin_ok(self, request, client):
        # Fail closed (review fix #4): a client with no configured origins is rejected,
        # so the exact-origin check can never be skipped by omission. The model + admin
        # also require at least one origin (ApiClient.clean).
        if not client.allowed_origins:
            return False
        raw = request.headers.get("Origin") or request.headers.get("Referer", "")
        if not raw:
            return False
        parts = urlsplit(raw)
        candidate = f"{parts.scheme}://{parts.netloc}" if parts.scheme else ""
        return candidate in set(client.allowed_origins)
```

- [ ] **Step 4: Run + commit**

```bash
docker compose exec backend pytest tests/test_apiclients.py -q   # all PASS
git add backend/apps/inventory/middleware.py backend/tests/test_apiclients.py
git commit -m "feat(apiclients): multi-client HMAC middleware with per-client origins"
```

---

## Task 17: Seed an ApiClient for the existing frontend (non-breaking)

**Files:**
- Modify: `backend/apps/inventory/management/commands/seed_demo.py`

- [ ] **Step 1:** In `seed_demo`, create (idempotently) an `ApiClient` whose secret is the
current `HMAC_SECRET` so the existing public frontend keeps signing successfully when
`API_CLIENT_AUTH_REQUIRED` is later turned on. Set `client_id` explicitly from
`HMAC_CLIENT_ID` and `allowed_origins` from `CORS_ALLOWED_ORIGINS`. Skip if
`HMAC_CLIENT_ID`/`HMAC_SECRET` are empty.

```python
from django.conf import settings
from apps.apiclients.models import ApiClient

# review fix #3: do NOT use get_or_create — secret_encrypted is non-null with no default,
# so a create() without it would crash. Fetch-or-instantiate, then set the secret.
if settings.HMAC_CLIENT_ID and settings.HMAC_SECRET:
    client = ApiClient.objects.filter(client_id=settings.HMAC_CLIENT_ID).first()
    if client is None:
        client = ApiClient(client_id=settings.HMAC_CLIENT_ID, label="Legacy frontend")
    client.allowed_origins = list(settings.CORS_ALLOWED_ORIGINS)
    client.set_secret(settings.HMAC_SECRET)
    client.save()
```

- [ ] **Step 2:** Run `docker compose exec backend python manage.py seed_demo` → no errors;
re-running is idempotent.

- [ ] **Step 3: Commit**

```bash
git add backend/apps/inventory/management/commands/seed_demo.py
git commit -m "feat(apiclients): seed legacy frontend client in seed_demo"
```

---

## Task 18: Audit log app + append-only model + `record()` service (`apps/audit/`)

**Files:**
- Modify: `backend/config/settings.py` (add `"apps.audit"`)
- Create: `backend/apps/audit/__init__.py`, `apps.py`, `models.py`, `services.py`
- Test: `backend/tests/test_audit.py`

- [ ] **Step 1: Add failing tests**

`backend/tests/test_audit.py`:

```python
import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import User
from apps.audit import services
from apps.audit.models import AuditLog
from apps.makerspaces.models import Makerspace

pytestmark = pytest.mark.django_db


def _user(username="su", role=User.Role.SUPERADMIN):
    return get_user_model().objects.create_user(
        username=username, email=f"{username}@e.com", role=role
    )


def test_record_creates_entry():
    actor = _user()
    s = Makerspace.objects.create(name="L", slug="l")
    entry = services.record(actor, "auth.login", makerspace=s, entity_id="42")
    assert entry.pk and entry.action == "auth.login"
    assert entry.actor_id == actor.id and entry.makerspace_id == s.id
    assert entry.entity_id == "42"


def test_auditlog_is_append_only():
    entry = services.record(_user(), "auth.login")
    entry.action = "tampered"
    with pytest.raises(ValueError):
        entry.save()
    with pytest.raises(ValueError):
        entry.delete()
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec backend pytest tests/test_audit.py -q`
Expected: FAIL (`ModuleNotFoundError: apps.audit.models`).

- [ ] **Step 3: Implement app config, model, service**

`apps/audit/apps.py`:

```python
from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
```

`apps/audit/models.py`:

```python
from django.conf import settings
from django.db import models

from apps.makerspaces.models import Makerspace


class AuditLog(models.Model):
    """Append-only record of a state-changing action (PRD §11)."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    makerspace = models.ForeignKey(
        Makerspace, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=100, blank=True)
    entity_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["makerspace", "action", "created_at"])]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("AuditLog is append-only; entries cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("AuditLog is append-only; entries cannot be deleted.")

    def __str__(self):
        return f"{self.action} by {self.actor_id} @ {self.created_at:%Y-%m-%d %H:%M}"
```

`apps/audit/services.py`:

```python
from apps.audit.models import AuditLog


def record(actor, action, *, makerspace=None, entity_type="", entity_id="", metadata=None):
    """Append one audit entry. Anonymous/None actor is stored as null (system action)."""
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        makerspace=makerspace,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        metadata=metadata or {},
    )
```

- [ ] **Step 4: Migrate + test + commit**

```bash
docker compose exec backend python manage.py makemigrations audit
docker compose exec backend python manage.py migrate
docker compose exec backend pytest tests/test_audit.py -q   # PASS
git add backend/config/settings.py backend/apps/audit backend/tests/test_audit.py
git commit -m "feat(audit): append-only AuditLog model + record() service"
```

---

## Task 19: Read-only scoped audit-log admin (superadmin all; admin if granted)

**Files:**
- Create: `backend/apps/audit/admin.py`
- Modify: `backend/config/unfold.py` (sidebar entry)
- Test: `backend/tests/test_audit.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_audit.py`:

```python
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from rest_framework.test import APIRequestFactory

from apps.audit.admin import AuditLogAdmin
from apps.makerspaces.models import MakerspaceMembership


def _req(user):
    r = APIRequestFactory().get("/")
    r.user = user
    return r


def test_admin_module_permission_requires_grant_for_admin_role():
    admin_user = _user("a1", role=User.Role.ADMIN)
    ma = AuditLogAdmin(AuditLog, AdminSite())
    assert ma.has_module_permission(_req(admin_user)) is False  # not granted
    perm = Permission.objects.get(codename="view_auditlog")
    admin_user.user_permissions.add(perm)
    admin_user = get_user_model().objects.get(pk=admin_user.pk)  # refresh perm cache
    assert ma.has_module_permission(_req(admin_user)) is True


def test_admin_changelist_scoped_to_makerspace():
    a = Makerspace.objects.create(name="A", slug="a")
    b = Makerspace.objects.create(name="B", slug="b")
    services.record(_user("x"), "x.act", makerspace=a)
    services.record(_user("y"), "y.act", makerspace=b)
    admin_user = _user("a2", role=User.Role.ADMIN)
    MakerspaceMembership.objects.create(user=admin_user, makerspace=a, role="admin")
    ma = AuditLogAdmin(AuditLog, AdminSite())
    qs = ma.get_queryset(_req(admin_user))
    assert {e.makerspace_id for e in qs} == {a.id}


def test_superadmin_sees_all_and_admin_is_readonly():
    su = _user("s9")
    ma = AuditLogAdmin(AuditLog, AdminSite())
    assert ma.has_add_permission(_req(su)) is False
    assert ma.has_change_permission(_req(su)) is False
    assert ma.has_delete_permission(_req(su)) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec backend pytest tests/test_audit.py -k admin -q`
Expected: FAIL (`ModuleNotFoundError: apps.audit.admin`).

- [ ] **Step 3: Implement the admin**

`apps/audit/admin.py`:

```python
from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.accounts import rbac
from apps.accounts.models import User
from apps.audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):
    list_display = ("created_at", "action", "actor", "makerspace", "entity_type", "entity_id")
    list_filter = ("action", "makerspace", "created_at")
    search_fields = ("action", "entity_id", "actor__username")

    # Append-only + read-only in the admin.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        u = getattr(request, "user", None)
        # review fix #2: also require active access_status.
        if not (u and u.is_authenticated and u.is_active
                and u.access_status == User.AccessStatus.ACTIVE):
            return False
        if u.is_superuser or u.role == User.Role.SUPERADMIN:
            return True
        # Admins only if explicitly granted the view permission (superadmin grants it).
        return u.role == User.Role.ADMIN and u.has_perm("audit.view_auditlog")

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    # Admins see only their makerspaces' entries (superadmin: all).
    def get_queryset(self, request):
        return rbac.scope_by_makerspace(
            request.user, super().get_queryset(request), "makerspace_id"
        )
```

- [ ] **Step 4: Sidebar entry**

In `config/unfold.py`, add an "Audit Log" item gated by a predicate mirroring
`has_module_permission` (superadmin, or admin with `audit.view_auditlog`), linking to
`admin:audit_auditlog_changelist`.

- [ ] **Step 5: Run + commit**

```bash
docker compose exec backend pytest tests/test_audit.py -q   # PASS
git add backend/apps/audit/admin.py backend/config/unfold.py backend/tests/test_audit.py
git commit -m "feat(audit): read-only scoped audit-log admin, permission-gated for admins"
```

---

## Task 20: Emit audit entries for Phase-2 actions

**Files:**
- Modify: `backend/apps/accounts/views.py` (login, logout)
- Modify: `backend/apps/apiclients/admin.py` (client created)
- Test: `backend/tests/test_audit.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_audit.py`:

```python
from rest_framework.test import APIClient


def test_login_emits_audit_entry():
    get_user_model().objects.create_user(
        username="loguser", email="l@e.com", password="pw-strong-123",
        role=User.Role.ADMIN,
    )
    APIClient().post(
        "/api/v1/auth/login",
        {"username": "loguser", "password": "pw-strong-123"}, format="json",
    )
    assert AuditLog.objects.filter(action="auth.login", actor__username="loguser").exists()
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose exec backend pytest tests/test_audit.py -k login_emits -q`
Expected: FAIL (no audit entry yet).

- [ ] **Step 3: Wire emission**

In `LoginView.post` (after `serializer.is_valid`), before returning:

```python
from apps.audit import services as audit
# ...
        audit.record(serializer.user, "auth.login")
```

In `LogoutView.post`, after resolving the cookie, record the logout (actor resolved from
the token if possible, else None):

```python
        actor = None
        if cookie:
            try:
                actor = User.objects.filter(pk=RefreshToken(cookie).get("user_id")).first()
            except TokenError:
                actor = None
        audit.record(actor, "auth.logout")
```

In `ApiClientAdmin.save_model`, after creating a new client:

```python
        if new_secret:
            from apps.audit import services as audit
            audit.record(
                request.user, "apiclient.created",
                makerspace=obj.makerspace, entity_type="ApiClient", entity_id=obj.client_id,
            )
            messages.warning(request, f"Client secret ... : {new_secret}")
```

- [ ] **Step 4: Run + commit**

```bash
docker compose exec backend pytest tests/test_audit.py -q   # PASS
git add backend/apps/accounts/views.py backend/apps/apiclients/admin.py backend/tests/test_audit.py
git commit -m "feat(audit): emit entries for login, logout, api-client creation"
```

---

## Task 21: Full backend suite + manual smoke

- [ ] **Step 1:** `docker compose exec backend pytest -q` → all pass (incl. existing `test_public_inventory.py`).
- [ ] **Step 2:** `docker compose exec backend python manage.py check` → no issues.
- [ ] **Step 3 (HMAC regression, review fix #9):** confirm BOTH `GET /api/public/makerspaces/` and `GET /api/v1/public/makerspaces/` behave identically under the current HMAC config (both guarded when HMAC is enabled, both open when not). The existing public-inventory test plus a quick curl to each path is sufficient.
- [ ] **Step 4:** Manual auth smoke: create an admin user in Django admin, assign a makerspace membership, `POST /api/v1/auth/login`, confirm access token in body + `refresh_token` cookie with a non-empty `Max-Age`, then `GET /api/v1/auth/me` with the Bearer token → profile with makerspace scope. Suspend the user in admin → next `/api/v1/auth/refresh` returns 403.
- [ ] **Step 5:** Confirm the new admin surfaces work: as superadmin, create an `ApiClient` (secret shown once) and confirm an `apiclient.created` audit entry appears; as a makerspace admin, confirm you see only your makerspace's clients and audit entries (and audit only after being granted `audit.view_auditlog`).
- [ ] **Step 6:** Update `CLAUDE.md` (Project Status + conventions): `/api/v1/` versioning + deny-by-default DRF, the auth endpoints + CSRF model, the RBAC module (membership-role authority) as scoping authority, the dev cookie strategy, the **`apps/apiclients/` HMAC registry** (per-makerspace, admin-managed, encrypted secret) now powering `FrontendHMACMiddleware`, and the **`apps/audit/` append-only log** (superadmin sees all; admin scoped + permission-gated). Note the publishable-key/browser path + third-party onboarding remain Phase 10.

```bash
git add CLAUDE.md
git commit -m "docs: record Phase 2 auth/RBAC + apiclients + audit conventions"
```

---

## Self-Review Notes (coverage vs spec)

- Spec §2 token model → Tasks 1, 6, 7 (lifetimes, cookie attrs, rotation, CSRF). ✓
- Spec §4 endpoints → Tasks 6–9 (login/refresh/logout/me) + Task 10 OpenAPI. ✓
- Spec §5 RBAC (`can`, `scope_by_makerspace`, permission classes, mixin) → Tasks 3–5. ✓
- Spec §6 settings/CORS → Task 1. ✓
- Spec §7 frontend shell → Tasks 11–13 (in-memory token, silent refresh, 401-retry, /me gate). ✓
- Spec §9 tests (role matrix, cross-tenant denial, suspended, rotation, CSRF) → Tasks 3–9. ✓
- ApiClient HMAC registry (model/admin/middleware/seed) → Tasks 14–17. ✓
- Append-only audit log (model/service/admin/emission) → Tasks 18–20. ✓
- Spec §10 docs + final verification → Task 21. ✓
