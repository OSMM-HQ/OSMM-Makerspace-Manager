# 3D Printing Manager — Implementation Plan

Spec: `docs/superpowers/specs/2026-06-09-3d-printing-manager-design.md`
App: `backend/apps/printing/` (new). All API under `/api/v1/`.

## Key integration constraint (must get right)

`apps/accounts/rbac.py::resolve_scope` and `permissions.py::IsStaff` currently key
authority on the **global** `User.role` (SUPERADMIN/ADMIN/GUEST_ADMIN). A
`print_manager` account's global role is `requester`; only its
`MakerspaceMembership(role=print_manager)` grants authority. So:

- **resolve_scope** must derive a non-superadmin's scope from their
  `MakerspaceMembership` rows **regardless of global `User.role`** (currently it
  returns `set()` unless global role is ADMIN/GUEST_ADMIN). Change the branch to:
  superadmin → `ALL`; any other authenticated user → set of membership
  `makerspace_id`s. This is more correct for the membership model and unblocks
  print_manager scoping. Existing Phase 2 tests must stay green.
- Printing manager endpoints **do not** use `IsStaff` (global-role gate). They use
  a new `CanManagePrinting` permission built on `rbac.can(..., MANAGE_PRINTING, ms_id)`
  plus an `access_status == ACTIVE` check.

## Step 1 — Role + models + migrations

**Files:** `apps/makerspaces/models.py` (+ migration),
`apps/printing/{__init__,apps,models,admin}.py`, `apps/printing/migrations/`,
`config/settings.py` (INSTALLED_APPS).

- Add `PRINT_MANAGER = "print_manager", "Print Manager"` to
  `MakerspaceMembership.Role`. Migration in `apps/makerspaces`.
- Create `apps.printing` app; register in INSTALLED_APPS after `apps.inventory`.
- `PrintBucket`: `makerspace` FK (CASCADE), `name`, `description` (blank),
  `is_active` (default True), `created_at`, `updated_at`; unique `(makerspace, name)`.
- `PrintRequest`: `bucket` FK (PROTECT), `requester` FK→User (PROTECT), `title`,
  `description` (blank), `material`/`color` (blank), `quantity`
  (PositiveIntegerField default 1, `MinValueValidator(1)`), `source_link`
  (URLField blank), `status` (choices pending/accepted/printing/completed/rejected/failed,
  default pending, db_index), `reason` (blank), `handled_by` FK→User (SET_NULL, null),
  `created_at`, `accepted_at` (null), `completed_at` (null), `updated_at`.
  Add `makerspace_id`/`makerspace` property reading `bucket.makerspace`.
  Add a `Status` TextChoices inner class.

## Step 2 — RBAC integration

**Files:** `apps/accounts/rbac.py`, `apps/printing/permissions.py` (new).

- `rbac.py`: add `Action.MANAGE_PRINTING = "manage_printing"`. Add to
  `_ADMIN_ACTIONS` (admins manage printing). Add
  `_PRINT_MANAGER_ACTIONS = {Action.MANAGE_PRINTING}` and map
  `MakerspaceMembership.Role.PRINT_MANAGER → _PRINT_MANAGER_ACTIONS` in
  `_MEMBERSHIP_ROLE_ACTIONS`. (Guest admins NOT added.)
- Update `resolve_scope` per the integration constraint above (membership-based
  for all non-superadmins).
- **Add action-aware scoping (Codex finding #1 — raw membership scope is NOT
  proof of an action):**
  - `makerspaces_for_action(actor, action)` → `ALL` for superadmin; else the set
    of `makerspace_id`s where the actor has a membership whose role grants
    `action` (via `_MEMBERSHIP_ROLE_ACTIONS`). Returns `set()` otherwise.
  - `scope_by_action(actor, action, queryset, field="makerspace_id")` → filters a
    queryset to `makerspaces_for_action`; `ALL`→unchanged, empty→`.none()`.
  - Manager printing querysets use `scope_by_action(user, MANAGE_PRINTING, qs,
    "bucket__makerspace_id")` — NOT plain `scope_by_makerspace` — so a
    `guest_admin` member (lacking `MANAGE_PRINTING`) sees nothing.
- `apps/printing/permissions.py`:
  - `IsActiveRequester` — authenticated + `access_status == ACTIVE`
    (for create/list-own; any active user may request — see community-model note
    in Step 5).
  - `CanManagePrinting(BasePermission)` — authenticated + `access_status == ACTIVE`;
    `has_permission`: if `?makerspace=` is provided, require
    `rbac.can(user, MANAGE_PRINTING, that_ms)` (else 403); if omitted, allow and
    rely on the action-scoped queryset (which is empty for non-managers, yielding
    an empty list, never a leak). `has_object_permission`: `rbac.can(user,
    MANAGE_PRINTING, obj.bucket.makerspace_id)`.

## Step 3 — Workflow service

**File:** `apps/printing/workflow.py`.

- `class InvalidTransition(Exception)`.
- `_ALLOWED = {pending:{accepted,rejected}, accepted:{printing}, printing:{completed,failed}}`.
- Functions `accept(request, actor)`, `reject(request, actor, reason)`,
  `start(request, actor)`, `complete(request, actor)`, `fail(request, actor, reason)`.
  Each, inside `transaction.atomic()`:
  1. **Re-fetch the row with `select_for_update()`** (Codex #4 — prevents
     concurrent accept/reject/start from double-writing status, audit, and email)
     and re-check the current status under the lock; raise `InvalidTransition`
     (→409) if the transition is no longer allowed.
  2. Set `status`, `handled_by=actor`, the relevant timestamp (`accepted_at` on
     accept, `completed_at` on complete), and **persist `reason`** on
     `reject`/`fail`.
  3. Call `apps.audit.record(actor, "print.<event>", makerspace=request.bucket.makerspace, target=request)`
     — **keyword args** `makerspace=` / `target=` (the real signature is
     `record(actor, action, *, makerspace=None, target=None, ...)`; positional
     would `TypeError`).
  4. Register `transaction.on_commit(...)` email dispatch (accept/reject/complete only).
- This is the ONLY module that writes `PrintRequest.status`.

## Step 4 — Email (SMTP + HTML)

**Files:** `config/settings.py`, `backend/.env.example`, `docker-compose.yml`,
`backend/templates/email/{base,print_accepted,print_rejected,print_completed}.html`
+ `.txt` siblings, `apps/printing/emails.py`.

- settings: `EMAIL_BACKEND` (default `django.core.mail.backends.console.EmailBackend`),
  `EMAIL_HOST`, `EMAIL_PORT` (587), `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
  `EMAIL_USE_TLS` (True), `DEFAULT_FROM_EMAIL`. All from env with safe dev defaults.
  Add `TEMPLATES[0]["DIRS"]` already includes `BASE_DIR/templates` — confirm.
- `base.html`: branded header (TinkerSpace `#FBB905`/`#111111`), `{% block body %}`.
- `emails.py`: `send_print_email(event, print_request)` renders subject + html/text
  via `render_to_string`, sends `EmailMultiAlternatives` to `requester.email`.
  Wrap send in try/except → structured `logger.warning` on failure, never raise.
  Skip silently if `requester.email` is blank.

## Step 5 — Serializers + views + urls

**Files:** `apps/printing/{serializers,views,urls}.py`, `config/urls.py`.

- **Community-model note (Codex #4 — make the rule explicit, not accidental):**
  this system is "public users browse and request" (CLAUDE.md). There is no
  requester↔makerspace membership, so **any active requester may create a print
  request against any *active* bucket in any makerspace — by design.** Buckets and
  makerspaces are public-facing, non-sensitive. To avoid a global dump, the bucket
  list endpoint **requires** an explicit `?makerspace=<id>` (400 if missing) and
  returns only that makerspace's active buckets.
- Serializers:
  - `PrintBucketSerializer` (read-only).
  - `PrintRequestCreateSerializer` — **field whitelist** = `bucket`, `title`,
    `description`, `material`, `color`, `quantity`, `source_link` ONLY. `status`,
    `reason`, `handled_by`, `requester`, and all timestamps are **excluded /
    read-only** (Codex #5 — never client-controlled). Validates the bucket exists
    and `is_active`; sets `requester = request.user` in `create()`; validates
    `quantity >= 1`.
  - `PrintRequestSerializer` (read; nested bucket label + makerspace id + status).
  - `RejectFailSerializer` (`reason` required, non-blank).
  - Action response serializers for OpenAPI.
- Requester views (perm `IsActiveRequester`): `PrintRequestCreateListView`
  (POST create / GET own — queryset filtered `requester=request.user`),
  `PrintRequestDetailView` (GET own only — `requester=request.user`),
  `PrintBucketListView` (GET active buckets, **mandatory** `?makerspace=`).
- Manager views (perm `CanManagePrinting`):
  `ManagedPrintRequestListView` — queryset `PrintRequest.objects.all()` scoped via
  `rbac.scope_by_action(user, MANAGE_PRINTING, qs, "bucket__makerspace_id")`
  (action-aware, Codex #1); filters `?status=&bucket=`. Action views
  `accept/reject/start/complete/fail` — fetch object from the **action-scoped**
  queryset (cross-tenant → 404), run `has_object_permission`, call workflow fn,
  map `InvalidTransition`→409, return updated request. `ManagedPrintRequestDetailView`
  — GET one (action-scoped). `PrintedListView` — action-scoped, completed-only.
- All endpoints `@extend_schema` documented (request/response, 401/403/404/409).
- Wire `path("api/v1/printing/", include("apps.printing.urls"))` in `config/urls.py`.

## Step 6 — Admin (unfold), tenant-scoped

**File:** `apps/printing/admin.py`. Follow the tenant-scoping pattern in
`apps/apiclients/admin.py` (Codex #6 — not a basic `ModelAdmin`).

- `PrintBucketAdmin`: superadmin sees all; an admin sees/edits only buckets in
  their makerspaces. Override `get_queryset` (filter to
  `rbac.resolve_scope`/membership makerspaces) and `formfield_for_foreignkey` to
  limit the `makerspace` choices to the admin's makerspaces.
- `PrintRequestAdmin`: read-mostly; `status`, `reason`, `handled_by`, timestamps
  are read-only (transitions go through the workflow service, never admin).
  `get_queryset` scoped via `bucket__makerspace`. `list_display`:
  status/bucket/requester/created.

## Step 7 — Tests (Stage 3)

**File:** `backend/tests/test_printing.py`.

Behavior coverage per spec + Codex #7:
- create/list/view own + scoping/pagination.
- each transition writes audit + sends email — assert via
  `@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")`
  AND `django.test.TestCase.captureOnCommitCallbacks(execute=True)` so the
  `on_commit` dispatch actually runs (otherwise `mail.outbox` stays empty).
- invalid transition → 409 with **no** audit row and **no** email.
- RBAC matrix: requester can't manage; print_manager manages only own makerspace;
  admin/superadmin scope; cross-tenant detail/action → 404.
- **guest_admin with a membership but no `MANAGE_PRINTING`**: manager list with
  `?makerspace=` omitted returns empty (action-aware scope), and with their own
  `?makerspace=` returns 403.
- requester creating against **another makerspace's** bucket (allowed by design)
  AND against an **inactive** bucket (rejected 400); invalid/non-numeric
  `?makerspace=` query param handled gracefully (400, not 500).
- concurrent-transition safety: a second `accept` on an already-accepted request
  returns 409 and does not duplicate audit/email.
- restricted/suspended requester blocked from create (403).
- email templates render (subject + branded header present) for each event.
- `printed/` returns only completed jobs, action-scoped.

## Risks / notes

- `resolve_scope` change is the highest-risk edit — re-run full Phase 2 suite.
  Manager scoping uses the new **action-aware** `scope_by_action`, not the broadened
  `resolve_scope`, so widening `resolve_scope` cannot leak printing lists to
  non-managers.
- Console email backend default keeps local/dev/CI runnable with no SMTP.
- `quantity` min validation enforced at serializer + model validator.
- Bucket→makerspace derivation means no separate makerspace field on PrintRequest
  (single source of truth, avoids drift).
- Open requester→any-makerspace request creation is **intentional** (community
  public-request model), documented in Step 5; bucket list still requires an
  explicit `?makerspace=`.
- Workflow-owned fields (`status`/`reason`/`handled_by`/timestamps/`requester`) are
  excluded from all client-writable serializers; transitions only via the workflow
  service, guarded by `select_for_update()`.
