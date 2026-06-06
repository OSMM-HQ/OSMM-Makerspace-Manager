# Phase 2 — Auth + RBAC + Makerspace Scoping + API Foundation (Design)

**Date:** 2026-06-07
**Status:** Approved (brainstorming) — pending written-spec review
**Depends on:** existing models (`User`, `Makerspace`, `MakerspaceMembership`).
**Governs everything after it:** the shared RBAC/scoping layer and API foundation are
reused by Phases 3–10.

This is the first sub-project of the multi-client backend
(`2026-06-07-backend-multiclient-architecture-design.md`). It delivers staff login,
the permission/scoping gatekeeper, and the API-first skeleton — including the
browser-facing publishable-client gate that connects the existing public frontend.

---

## 1. Goal

1. Staff (superadmin / admin / guest-admin) can log into a separate-origin admin frontend.
2. Every staff query is permission-checked and **scoped to assigned makerspaces**;
   superadmin sees all.
3. The API gains a versioned `/api/v1/` namespace (CORS-allowlisted) for the new auth and
   future staff surface. Existing public routes keep working and are aliased under
   `/api/v1/` (non-breaking).
4. `restricted`/`suspended` accounts are blocked.

Non-goals here (decided at plan time): the `ApiClient` registry / publishable keys / HMAC
server-signing — **all deferred to Phase 10**. The existing single-client
`FrontendHMACMiddleware` (`apps/inventory/middleware.py`) stays untouched and keeps
guarding the public surface. Also out of scope: request workflow, evidence, QR, and a
user-management REST API (staff are managed in the Django admin).

## 2. Decisions locked (from brainstorming)

- **JWT** via `djangorestframework-simplejwt`.
- **Access token** ~15 min, returned in login body, held in React memory.
- **Refresh token** ~7 days, `HttpOnly; Secure; SameSite=None`, path-scoped to
  `/api/v1/auth/refresh`; rotated + blacklisted on each use; cleared on logout.
- **CSRF guard on refresh:** required custom header (double-submit) since `SameSite=None`
  ships the cookie cross-site. CORS blocks reading the rotated token; the header blocks
  blind cross-origin triggering.
- **Separate origins:** credentialed CORS allowlist, one entry per registered frontend.
- **Provisioning:** staff created/assigned in the themed Django admin (existing
  `MakerspaceMembership` inline). No user-management REST API this phase.

## 3. Data model

No new domain tables. Django `User` + `MakerspaceMembership` already exist and are
sufficient. The `ApiClient` registry is **not** built here (Phase 10).

Add `simplejwt`'s token blacklist app (its migrations) for refresh rotation/revocation.

## 4. Endpoints (all drf-spectacular documented)

| Method/Path | Auth | Behavior |
|---|---|---|
| `POST /api/v1/auth/login` | open (CORS-gated) | username/email + password → `{access, user, role, makerspaces}` in body; sets refresh cookie |
| `POST /api/v1/auth/refresh` | refresh cookie + CSRF header | new access token; rotates refresh cookie |
| `POST /api/v1/auth/logout` | refresh cookie | blacklists refresh token; clears cookie |
| `GET  /api/v1/auth/me` | JWT | current user + role + scoped makerspaces |

Built as thin subclasses of `TokenObtainPairView` / `TokenRefreshView` that relocate the
refresh token from the body into the cookie and enforce the CSRF header on refresh.

The existing public routes (`/api/public/...`) keep working unchanged and are **also
aliased** under `/api/v1/` (so `/api/v1/public/:slug/inventory/` resolves too). The
`FrontendHMACMiddleware` prefix list is widened to cover both. No frontend change required.

## 5. RBAC module — `apps/accounts/rbac.py`

The load-bearing layer. Single source of truth for permissions + scoping.

```text
can(actor, action, resource) -> bool
    # 4-role matrix (PRD §4). e.g. accept/reject → admin(scoped)|superadmin;
    # issue → admin|guest_admin|superadmin (scoped); edit_inventory → admin|superadmin.

scope_by_makerspace(actor, queryset) -> queryset
    # superadmin: unchanged. admin/guest-admin: filtered to makerspace ids from
    # their MakerspaceMembership. requester/none: empty.

resolve_scope(actor) -> set[makerspace_id] | ALL
```

DRF integration:

- `DEFAULT_AUTHENTICATION_CLASSES`: `JWTAuthentication` (access token from
  `Authorization: Bearer`).
- Permission classes: `IsSuperadmin`, `IsMakerspaceAdmin`, `IsGuestAdmin`,
  composed/parametrized as needed.
- `MakerspaceScopedQuerysetMixin` — applies `scope_by_makerspace` in `get_queryset`,
  so no future admin view re-implements scoping (enforced, not convention).
- Login rejects accounts where `is_active` is false or `access_status != active`.

## 6. Settings / infrastructure

- `simplejwt` config: access 15m, refresh 7d, rotation on, blacklist on.
- Cookie attrs centralized: `HttpOnly`, `Secure`, `SameSite=None`, `Path=/api/v1/auth/refresh`.
- `CORS_ALLOWED_ORIGINS` from env/config (credentialed); replace the dev-only port pair.
- `django-cors-headers` already present? add if missing.

## 7. Frontend auth shell (`frontend/`)

Minimal — the shell the Phase 3 approvals screen drops into, not the screen itself.

- **Auth context** holding the in-memory access token (lost on reload by design).
- **Login page** → calls `/auth/login`, stores access token, refresh cookie set by server.
- **Silent refresh on app load** → calls `/auth/refresh` (cookie) to restore session after
  reload; on failure, route to login.
- **API client wrapper** (fetch/axios) attaches `Authorization: Bearer`; on `401`, tries
  one `/auth/refresh` then retries, else logs out.
- **Protected layout** gated by `GET /auth/me` (role available for conditional nav).

Maps React/TanStack Query concepts: access token = client state in context; `me` query =
server state; the 401→refresh→retry is interceptor logic, not query cache.

## 8. Error handling

Consistent typed JSON errors:

- `401` invalid credentials / missing-expired access token.
- `401` + `token_not_valid` on refresh → frontend logs out.
- `403` forbidden action (role) / wrong makerspace (scope).
- `403` suspended/restricted staff at login.

## 9. Testing (PRD §17 — external behavior)

- Role matrix: each role allowed/denied the right actions via `can(...)`.
- **Cross-tenant denial:** admin of A cannot retrieve B's scoped queryset
  (`scope_by_makerspace` returns empty / 403).
- Suspended/restricted staff cannot log in.
- Refresh rotation: old refresh token rejected after use; logout invalidates refresh.
- CSRF: refresh without the custom header is rejected.

## 10. CLAUDE.md / docs updates after build

- Note the `/api/v1/` versioning + public/staff split as the standing convention.
- Document the three identity layers and the RBAC module as the scoping authority.
- Update `docs/roadmap.md` to the revised phase order (incl. Phase 8 transfer).
