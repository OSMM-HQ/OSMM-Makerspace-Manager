# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **On this file's structure.** The durable, load-bearing rules live in the lower half
> ("Cross-cutting invariants", "Project Status", "Engineering Conventions", "Architecture",
> "Hard Rules"). The chronological batch history was condensed into the "Condensed changelog"
> — full detail lives in `git log` and in the assistant's memory files. When editing a shipped
> feature, prefer `git log`/`git blame` for its history; use the invariants section for the rules
> you must not regress.

## Current work — FabLab expansion (branch `dev`)

Active multi-part FabLab program built on `dev` via a **Codex-driven workflow** (Codex writes specs
and code in parallel where files don't collide; Claude orchestrates, verifies each phase, and commits
phase-per-commit with three co-author trailers). Per user direction, the **single user QA is deferred
to the very end** (after all Parts) — no per-Part QA gate. Specs live (gitignored) under
`docs/superpowers/specs/2026-07-1*`.

**Shipped on `dev` (see condensed changelog for the module list):** Events, Bookings, Maintenance,
Analytics/reports, public Roadmap, Machine Manager role + delegated role assignment, public
self-booking + shared custom forms, per-feature×per-channel notification matrix (Slack/Mattermost),
scoped PII encryption (Parts H1–H4), custom editable per-makerspace roles (Part L). In flight: Part N
(machine service requests, in a git worktree) and Part M (member accounts) — detailed live state is
tracked in the assistant's memory, not here.

**Standing build conventions for this program:**
- **Parallel Codex via git worktree.** A second track runs in a sibling worktree
  (e.g. `../IM-nbuild` on its own branch) with a dedicated test DB, so two Codex builds don't collide
  on shared files (`rbac.py`, `origin_scope.py`, `admin_api/urls.py`, `openapi-schema.json`, `api.ts`).
  Worktrees are fresh checkouts → **gitignored files (e.g. `backend/.env`) must be copied in**. Cap at
  2 heavy builds. At the end: merge the worktree branch → `dev`, `git worktree remove`, drop its DB.
- **Codex gotchas.** Run Codex with skill-free prompts that skip reading this file, in the
  **background** (`run_in_background:true`) — the 10-min foreground ceiling is too short. Stage-4 =
  `codex exec review --uncommitted` (no `--sandbox`, no custom prompt; findings at the literal tail).
  If Codex dies with Windows `-1073741502` / "host exited during handshake", it's desktop-heap
  exhaustion — kill **only** codex PIDs (never `node.exe` = harness/MCP); a reboot clears it.
  **Never `git add`/stage before a Codex workspace-write run** — a non-empty staged index makes
  Codex's `apply_patch` silently fail with a misleading "workspace/tests/ is read-only" or
  "staged index is read-only" error (no files written). Keep the index clean during
  implementation; only `git add` right before the Stage-4 `codex review` (so it sees new
  untracked files), then `git reset` before the next Codex build.
- **Test harness.** Local `spaceworks-db` (:5433), `spaceworks-redis`, `spaceworks-minio` (:9100) must be running. Run
  tests with `DATABASE_URL="postgres://makerspace:makerspace@localhost:5433/makerspace_manager"` (or
  the worktree's dedicated DB). **Never run two `pytest` procs against one DB** (TRUNCATE-FK teardown
  races + false concurrency failures) and **never run the full suite concurrently with `codex review`**
  (it runs its own pytest). If a background full-suite is killed by the environment, run it as
  **foreground chunks** (`pytest tests/<subdirs>`, `tests/test_[a-l]*.py`, `tests/test_[m-z]*.py`).
  Pre-existing non-regression: `test_machine_image_presign_finalize_delete_and_audit` fails because
  MinIO is on :9100 vs the test default :9000.
- **Migration heads drift.** Specs quote stale migration numbers; every Codex prompt must
  `ls backend/apps/<app>/migrations/` and chain off the **actual** leaf, not the spec number. A new
  migration whose dep is a rewound app can break migration-executor tests (rewind the full graph
  forward in the test's `finally`).

## Cross-cutting invariants (from shipped batches — do not regress)

These rules were established across many batches and are load-bearing beyond any single module:

**Self-host vs managed SaaS (all managed features dormant by default).** `PLATFORM_DOMAIN_SUFFIX`
blank/whitespace ⇒ `domain_verification.is_self_host()` is True ⇒ **every managed feature is inert**
and single-domain behavior is byte-for-byte unchanged (self-hosters unaffected). Self-host trusts a
superadmin-set custom `frontend_domain` immediately (no DNS TXT challenge — the challenge only ever
defended the shared managed box). The self-host branch is strictly superadmin-only (the staff-origin/
CORS allowlist is process-global; letting any tenant set a trusted origin is a cross-tenant token-theft
vector). Managed mode adds `<slug>.space-works.tech` provisioning + tenant self-serve custom domains on one
shared instance (no per-tenant DB). **VERIFIED is the trust gate** — a `frontend_domain` grants CORS/
staff-origin/bootstrap/Host/TLS trust only when `frontend_domain_status=VERIFIED` and non-archived.

**Managed fair-use limits (dormant on self-host).** `apps/makerspaces/limits.py` `resource_limit(ms, key)`
(self-host → None = unlimited; per-space `resource_limit_overrides` JSON, else `MANAGED_RESOURCE_LIMITS`)
+ `check_quota(ms, key, *, adding)` called **inside each creation service's `transaction.atomic()`**
(self-locks the makerspace row; raises DRF 400 `{"limit": …}` / typed `limit_reached` at cap). Storage
counter (`add_storage`/`free_storage`) charged at finalize; `recompute_storage` management command is the
authoritative reconciler. Email daily cap via `integrations.DailyEmailCounter`.

**One domain per makerspace.** `Makerspace.frontend_domain` (case-insensitively unique) is the single
frontend-registry field (the old per-type `TenantFrontend` model is deleted). Two origin helpers in
`platform.py`: `makerspace_staff_origins` (ONLY the exact `https://<frontend_domain>`, feeds refresh/
logout CSRF + the origin→tenant guard) vs `makerspace_public_origins` (that ∪ `cors_allowed_origins`,
feeds general CORS + publishable-key validation) — so an API-client/public origin can make
publishable-key calls but **can never mint a staff session**. `origin_scope.py` hard-scopes a browser
staff request to its domain's makerspace; origin-less (server) requests fall back to `MakerspaceMembership`.

**Superadmin access is a HARD block, not a soft hide.** `Makerspace.superadmin_access_enabled=False`
excludes the space for a GLOBAL superadmin across `rbac.can`/`scope_by_action`/`makerspaces_for_action(s)`
etc. (a superadmin with an explicit membership keeps only that role's actions). Status contract: hidden
→ **403** on action/permission-gated endpoints, **404** on object-lookup detail + re-enable PATCH,
**empty 200** on scope-filtered lists. Existence stays visible as a slim row (governance). True→False is
rejected unless Platform Email is configured (forgot-password recovery). Re-enable is space-manager-only.
Break-glass: superadmin may create a fresh SPACE_MANAGER / reset a hidden-only SM. Application-layer only
(DB/`manage.py` access always overrides).

**Makerspace archive → purge (superadmin, `/control/` only).** `Makerspace.archived_at` is the
single soft-delete flag; archive scoping is threaded through central rbac + all aggregates + public +
token-status surfaces (archived is invisible everywhere but `/control/`). `lifecycle.py` is the single
lifecycle source. **Purge** is break-glass: collects S3 keys, writes a platform-scoped audit, then in
one `transaction.atomic()` suspends immutability triggers **transaction-scoped** and deletes the full
`PROTECT` object graph in verified dependency order, then best-effort deletes S3.
- Self-host: `SET LOCAL session_replication_role='replica'` (all triggers off; FK off — ORM does
  CASCADE/SET_NULL in Python).
- Managed Postgres (`MANAGED_POSTGRES=True`, e.g. Supabase forbids `session_replication_role`):
  `SET LOCAL app.allow_immutable_delete='on'` (only OUR immutability triggers bypass; FK stays on).
- **Every append-only/immutability trigger is purge-aware**: DELETE allowed only under GUC
  `current_setting('app.allow_immutable_delete', true)='on'`; UPDATE always blocked (audit/0003 style).
  A new PROTECT-FK + immutable model must add itself to the purge graph **and** the drift-guard.

**Object storage.** Two buckets per env: a private evidence/docs bucket and a separate **public-read**
image bucket (`PUBLIC_IMAGE_BUCKET`, served via `PUBLIC_IMAGE_BASE_URL`, kept distinct from the signing
host). New file types use the **prefix model** (single shared bucket, isolated by
`<module>/<makerspace_id>/<machine_or_resource_id>/<category>/<uuid>` — NOT bucket-per-makerspace, which
would hit S3's ~100-bucket limit) — applied to NEW files only, no re-keying. Presign follows
`STORAGE_PRESIGN_METHOD` (POST for MinIO, PUT for Supabase; PUT-mode re-validates size server-side at
attach). Object keys are identifiers, not secrets — privacy is the private bucket + short-lived signed
URLs. Upload validation: strict magic-sniff for PDF/image; the private maker/CAD allowlist
(`apps/maker_file_formats.py`) accepts STL/OBJ/3MF/STEP/etc. on ext+MIME (+signature for 3MF/STEP);
public-image + evidence buckets stay strictly image-only.

**Reports/analytics extend one registry** (never a parallel system). `apps/operations/report_registry.py`
holds canonical `ReportDefinition`s (module-gated, `report_scope.eligible_makerspaces` excludes archived
+ reports-disabled + superadmin-hidden). FabLab domain builders (`reports_events`/`_bookings`/
`_maintenance`/`_machine_usage`/`_inventory` + fail-safe `reports_health`) mirror printing's date-range
contract; **aggregate output groups by `makerspace_id` and never flattens cross-tenant data**. Per-makerspace
report rows are gated by query-level scope (no per-row Python check → no N+1).

**Scoped PII encryption (Part H, `apps/encryption/`; dormant unless enabled).** Per-makerspace DEK via a
key broker (local/AWS-KMS), AAD-authenticated envelope crypto, `ScopedPiiModelMixin` on the 6 PII-holding
models with a save-boundary that single-INSERTs envelopes + dual-read cache. Blind-index search
(domain-separated HMAC bloom + exact + event-email hashes) for enabled deployments; disabled deployments
search plaintext via ORM. Write-fence (`PiiGlobalWriteFence`/`PiiMakerspaceWriteFence` + PG
`pii_assert_mapped_write_allowed()` triggers with global-then-tenant advisory locks) blocks mapped writes
during maintenance; mapped services acquire the fence **before** their domain row lock. Enabling is a
staged dual-read rollout; `decrypt_scoped_pii` is the fenced rollback. **Encryption is never enabled
before H3 (search) ships.**

**Custom editable per-makerspace roles (Part L).** The 5 legacy roles are now editable protected default
`Role` rows; authority is **action-based** via the assigned role (dual-read with legacy fallback:
`rbac.actions_for_membership` resolves assigned-role-first, tenant-match-else-fail-closed, strips
unknown/forbidden actions, null-FK → frozen legacy). `can()`/`makerspaces_for_action()`/hidden-block all
route through it. `/auth/me` + `/auth/login` carry typed effective `actions` per membership; the frontend
`staffAccess.ts` derives every capability from action strings, not role names. Role CRUD +
membership/role-assignment APIs enforce non-escalation (can't grant a role you don't hold; can't touch a
MANAGE_MAKERSPACE target/role) with makerspace-first lock ordering.

**Console parity principle.** Every backend lifecycle capability reachable in the Django `/control/`
admin must have a React staff-console surface — a capability with no console surface is a latent
dead/broken feature for normal staff. New workflow actions ship their staff UI in the same batch.

## Condensed changelog (newest first — full detail in `git log`)

Each line names a shipped feature and, where useful, the load-bearing rule it introduced (folded into the
invariants above). Use `git log --oneline`/`git blame` for the implementing commits and per-file history.

- **FabLab Parts C–N + L + H + Settings + K** (2026-07-16→18, `dev`): Events, Bookings (+ public
  self-booking + shared `forms_schema` custom forms + structured event location), Maintenance, Analytics
  reports, public Roadmap, Machine Manager role + SM-delegated role assignment, per-feature×per-channel
  notification matrix (Slack/Mattermost), scoped PII encryption H1–H4, custom roles L, machine service
  requests N (in worktree). New apps: `events`, `bookings`, `maintenance`, `roadmap`, `forms_schema`,
  `encryption`, machine-service models under `machines`.
- **Machines module M1 + M1.5** (2026-07-14/15): generic `apps/machines/` (types/machine/operators/usage/
  docs/errors), 3-tier authz (`MANAGE_MACHINES` + type-managers via `MachineType.managing_action` +
  per-machine operators), services single-source-of-truth, printer auto-link, custom types, photo,
  warranty (3rd host), consumables (count via inventory + grams ledger), public exposure.
- **Self-host-first + SaaS hosting Parts A/B + space-works.tech** (2026-07-15/16): self-host custom-domain
  auto-trust, managed fair-use limits + subdomain request→approve, one-shared-instance multi-tenant
  hosting (all dormant on blank `PLATFORM_DOMAIN_SUFFIX`). AGPL relicense + repo professionalization.
- **Audit fixes + dependency upgrade P1–P17** (2026-07-08): integration health center, scan-first
  stocktake, ops dashboard, notifications app + inbox + fail-safe emit hooks; force-latest upgrade to
  Django 6 / React 19 / Vite 8 / Tailwind 4 / TS 6.
- **Manager fixes P5–P10** (2026-06-30): direct-loan return resolutions + accountability + public
  report-a-problem, unified asset editor, optional partial approval, accountability dashboard,
  actionable warranty/reports UI.
- **Email/async stack** (2026-06-21): `EmailLog` outbox + single `dispatch_email` choke point + Celery/
  Redis async delivery + retry. Per-makerspace staff-notification recipient matrix.
- **Print filament grams / payment / manual logs** (2026-06-16/28): requester grams estimate, failed-%
  → printer hours, manual-log outcomes, staff-private cash payment on prints (never exposed to requester
  — enforced by serializer split), top-requesters leaderboard by email.
- **Warranty tracking** (2026-06-27): `apps/warranty/` (asset XOR printer XOR machine host, private
  bill/doc uploads, display-only status; per-host RBAC; public-leak invariant tested).
- **UI reskins** (frontend-only): pastel "notebook" theme (2026-06-22, fill/`-ink` token split),
  Blueprint redesign + item/makerspace imagery (2026-06-20).
- **Collaborative self-governance** (2026-06-16): superadmin-access toggle (later hard block),
  API-client self-serve, admin + self-service password resets, Platform Email settings.
- **Console-parity + workflow surfacing** (2026-06-16): broken-at-handover + to-be-fixed shelf,
  ledger specific-unit + staff-return evidence, direct-handout UX, lending history, QR rebind,
  surfacing ~10 orphaned backend lifecycles into the React console.
- **Deploy / production** (2026-06-19): single-tenant branded frontend, Supabase free-tier dual-mode
  (env-toggled; localhost default unchanged), lean-paid production deploy artifacts + perf hardening.

## Project Status

### Admin control plane (superadmin-only)

The **Unfold Django admin is the Super Admin's sole control plane**, mounted at **`/control/`**
(NOT `/admin/` — `/admin` belongs to the React staff console SPA route), locked to superadmins, and
**not exposed on the public frontend port** (`frontend/nginx.conf` does not proxy it — makerspace staff
on port 80 can never reach the Django console; the superadmin reaches `/control/` only via direct backend
access). Gated two ways: `config.admin_access.AdminSuperuserOnlyMiddleware` (denies any authenticated
non-superadmin; the `/api/v1/admin/...` React staff APIs are NOT gated) and
`config.admin_access.SuperuserOnlyModelAdmin` (first base of every `ModelAdmin`). Superadmin operations
are Django admin **actions that route through the existing services** (never mutating status directly);
issue/return remain React-only. Superadmin monitoring surfaces (QR ZIP, inline QR/photo previews, print
file downloads) are read-only and guard storage failures.

**U-SEC:** django-axes admin-login lockout, scoped `login`/`public_request_submit` throttles + write-only
`website` honeypot on public submit, production-gated security headers, always-on CSP via django-csp 4,
and a `pip-audit` CI job. The global CSP `script-src` omits `'unsafe-eval'`; a tiny
`config.admin_access.AdminCspEvalMiddleware` appends `'unsafe-eval'` to `script-src` **and** the S3 public
origin to `img-src` **only for `/control/` responses** (django-unfold ships eval-requiring Alpine.js; the
JSON API + public docs stay on the strict policy). Design spec:
`docs/superpowers/specs/2026-06-13-superadmin-admin-control-plane-design.md`.

**Django admin coverage** is complete (every domain model registered; immutable/workflow-owned models
read-only; a `list_filter` per makerspace-scoped admin). The Unfold sidebar (`config/unfold.py`) is
curated into grouped sections; a test asserts every sidebar link resolves. A drift-guard test
(`tests/test_admin_hidden_scope.py`) walks every registered admin and forces an explicit scoped/global
decision (via `NESTED_MAKERSPACE_LOOKUPS` / `GLOBAL_ADMIN_MODELS`) so a new admin can't silently leak
across the superadmin hide/archive scoping.

**Non-technical install:** `setup.sh` / `setup.ps1` (first-run wizard: Docker check → generate secrets
incl. Fernet `API_CLIENT_ENC_KEY` → write `.env` → build → `setup_instance` → print URL/creds),
`docker/compose.build.yml`, and `docs/setup-for-makerspaces.md`. TLS is env-gated (`ENABLE_HTTPS`,
default off). First-run `setup_instance` seeds `superadmin`/`super123` + `must_change_password` (surfaced
by login + `/auth/me`, cleared by `/auth/change-password`).

**Per-makerspace integrations are backend-only and never leak.** `Makerspace` holds per-tenant
`telegram_bot_token` + `smtp_*`; secrets are encrypted at rest with `API_CLIENT_ENC_KEY` via
`apps/makerspaces/secrets.py` and decrypted only in delivery code. The staff serializer exposes them
**write-only** + a `*_set` boolean. Bootstrap returns only frontend-safe config (module flags, not
secrets). No shared-integration entity exists — makerspaces sharing SMTP/Telegram enter the same
credentials per space (stored/encrypted independently).

**Implementation status.** The multi-frontend platform and open operations/reporting PRDs are implemented
end-to-end (public browse, auth/RBAC, API-client HMAC, QR/box, audit/evidence, 3D Printing Manager,
Hardware Request Workflow, procurement "To Buy", stock transfers incl. true cross-makerspace movement,
stocktake, analytics/ledger/exports, Users CRUD, the FabLab modules in the changelog). The detailed PRDs
(`docs/prd-*.md`) are **internal planning docs kept local only** (gitignored); "PRD §N" references point
to those. Google Sheets OAuth publishing, native apps, and physical label-printer control remain out of
scope.

Stack (in use):

- **Backend:** Django 6 + Django REST Framework (`backend/`). Requires Python 3.12+.
- **Frontend:** React 19 + Vite 8 + TypeScript (`frontend/`). Requires Node 20.19+ / 22.12+.
- **Server-state management:** TanStack Query v5
- **Database:** PostgreSQL 16 (via `docker-compose.yml`)
- **Styling:** Tailwind CSS 4 (CSS-first; `src/index.css` uses `@import "tailwindcss"` + `@config
  "../tailwind.config.ts"`; PostCSS via `@tailwindcss/postcss`) with CSS-variable light/dark theme tokens.
  Light default; dark toggle persisted locally.
- **API documentation:** drf-spectacular / OpenAPI (snapshot `frontend/openapi-schema.json` + generated
  `frontend/src/generated/api.ts`; regenerate both when routes/models change — spectacular needs
  `--format openapi-json`).
- **Admin theme:** django-unfold; site name via `ADMIN_SITE_NAME` (default "Space Works").
- **Telegram:** request alerts, test alerts, authenticated webhook accept/reject callbacks.

### Local development

```bash
# 1. Database
docker compose up -d db

# 2. Backend (from backend/)  —  copy .env.example to .env if needed
cd backend
pip install -r requirements.txt
python manage.py makemigrations accounts makerspaces inventory
python manage.py migrate
python manage.py seed_demo
python manage.py runserver            # http://localhost:8000

# 3. Frontend (from frontend/)
cd frontend
npm install
npm run dev                           # http://localhost:5000

# Tests (from backend/, DB must be up)
cd backend && pytest
```

- Public inventory page: `http://localhost:5000/m/makerspace`
- API: `http://localhost:8000/api` — Swagger UI at `/docs/`, ReDoc at `/redoc/`, schema at `/schema/`.

### Current source map (real paths)

- `backend/config/` — Django project (`settings.py`, `urls.py`, wsgi/asgi). All API routes under `/api/`.
  `config/admin_access.py` holds the `/control/` gating, CSP middleware, and the hidden-scope drift-guard
  registries (`NESTED_MAKERSPACE_LOOKUPS`, `GLOBAL_ADMIN_MODELS`).
- `backend/apps/accounts/` — custom `User` model (`AUTH_USER_MODEL`), JWT auth, and `rbac.py` (the Auth &
  RBAC module: `can(...)`, action-based `actions_for_membership`/`makerspaces_for_action`/`scope_by_action`,
  makerspace scoping, superadmin hide/archive exclusion).
- `backend/apps/makerspaces/` — `Makerspace` model (tenant root; unique `slug`; `frontend_domain`,
  module flags, `resource_limit_overrides`, `archived_at`, `superadmin_access_enabled`), bootstrap views,
  dynamic CORS, module guards, `platform.py` origin helpers, `limits.py` (fair-use quotas), `lifecycle.py`
  (archive/purge), `origin_scope.py` (browser origin→tenant guard), `provisioning.py`/`hosting.py`
  (managed subdomains), `secrets.py`.
- `backend/apps/audit/` — append-only `AuditLog` + `audit.record(...)` (Postgres-trigger immutable).
- `backend/apps/evidence/` — immutable evidence photos, S3 storage helpers, signed upload/view URLs gated
  by per-makerspace `UPLOAD_EVIDENCE` + active status.
- `backend/apps/boxes/` — `QrCode`/`Box` payloads, immutable `BoxScan`/`QrScanEvent`, `qr_render.py`
  (namespaced standalone SVG shared by QR-print + batch ZIP), QR rebind. Camera scanner at
  `frontend/src/components/ui/QrScanner.tsx` (native `BarcodeDetector` + `zxing-wasm` fallback).
- `backend/apps/admin_api/` — staff REST surface: makerspaces, inventory CRUD + per-makerspace category
  CRUD (`EDIT_INVENTORY`), bulk import, staff/membership + role management, user restrict/restore,
  API-client issuance, audit reads, warranty, email-log, notification-recipient, FabLab report views.
- `backend/apps/operations/` — open operations/reporting: health, stock transfers (intra + true
  cross-makerspace), stocktake, adjustments, ledger, `report_registry.py` + `report_scope.py` +
  `reports_*` builders, CSV/XLSX exports, container APIs, QR print batches (`qr_zip.py`), dashboard,
  accountability. `views.py`/`services.py` are thin re-export barrels over `views_*`/`services_*`.
- `backend/apps/integrations/` — Telegram/email/Slack/Mattermost delivery, `dispatch_email` choke point +
  `EmailLog` outbox + Celery task, webhook (auth via `X-Telegram-Bot-Api-Secret-Token` vs
  `TELEGRAM_WEBHOOK_SECRET`, fail-closed), `PlatformEmailSettings`, `DailyEmailCounter`, staff-notification
  recipient matrix.
- `backend/apps/inventory/` — `InventoryProduct`/`InventoryAsset`, `availability.py` (**the only place**
  available/reserved/issued/damaged/lost counts change: `reserve_for_request`, `issue_items`/`return_items`,
  `issue_available`/`return_to_available`, `consume_available`; row-locked, never-below-zero,
  `InsufficientStock`), `public_availability.py` (public availability service), allowlist-only public
  serializers/views, `public_image_storage.py`, `seed_demo`.
- `backend/apps/hardware_requests/` — Hardware Request Workflow: `HardwareRequest`/`HardwareRequestItem`,
  `HardwareRequestItemAsset` through-model, immutable `ReturnEvent`/`RequesterAccountability`,
  `PublicToolLoan`, `PublicProblemReport`. `workflow.py` is the **single source of truth** for state
  transitions (atomic + row-locked + audited; also `assign_box`/`issue_request`/`return_items`);
  `permissions.py`, `exceptions.py` (workflow→HTTP map + `ErrorSerializer._EXCEPTION_MAP`),
  `notifications.py` (Telegram seam), public submit/verify/status views, `send_return_reminders` command.
- `backend/apps/checkin/` — fail-closed Check-In API client (`verify()`, `CheckinUnavailable`→503 /
  `CheckinDenied`→403; `stub` vs `http` via `CHECKIN_MODE`).
- `backend/apps/printing/` — 3D Printing Manager: `PrintBucket`/`PrintRequest`/`PrintPrinter`/
  `FilamentSpool`/`ManualPrintLog`; `workflow.py` (single source of truth), `permissions.py`
  (`CanManagePrinting`), `emails.py`, `storage.py` (print upload presign), `reports_*`, public
  submit/status mirroring the hardware public posture (AllowAny + throttle + honeypot + no-PII status).
  `ManagedPrintRequestSerializer` (staff, price/payment) is split from the shared price-free serializer.
- `backend/apps/warranty/`, `apps/machines/`, `apps/maintenance/`, `apps/events/`, `apps/bookings/`,
  `apps/roadmap/`, `apps/forms_schema/`, `apps/encryption/`, `apps/procurement/`, `apps/notifications/`,
  `apps/operations/report_registry.py` — the FabLab + governance modules (see condensed changelog).
- `backend/tests/` — pytest behavior tests (external behavior, not implementation).
- `frontend/src/features/inventory/` — public catalog/detail/self-checkout + `ProductCard`/
  `AvailabilityBadge`. `frontend/src/features/staff/` — staff console panels (grouped nav via
  `StaffApp.tsx` `TAB_GROUPS`; capabilities from action-based `staffAccess.ts`). `frontend/src/features/
  printing|bookings|forms|...` — feature slices. `frontend/src/lib/`, `components/ui/`, `types/`,
  `generated/api.ts`.

### Public availability rule (resolves PRD §5's two overlapping fields)

`public_availability_mode` is the master display switch; `show_public_count` is a safety gate for exact counts:

- `is_public = false` → product excluded from the public list entirely.
- mode `hidden` → product listed, `availability: null`.
- mode `status_only` → `{ mode: "status_only", label }`.
- mode `exact_count` → exact `count` **only if** `show_public_count = true`; otherwise falls back to `status_only`.
- Status label: `available ≤ 0` or `total ≤ 0` → `Unavailable`; `available ≤ ceil(total × 0.2)` → `Limited`; else `Available`.

The API response is DRF-paginated (`PageNumberPagination`, page size 24): `{ count, next, previous, results }`. This is the standing convention for all list endpoints.

### Audit + evidence conventions

- Audit writes go through `apps.audit.services.record(actor, action, ...)`. `AuditLog` is append-only in
  model methods and by Postgres triggers; state-changing services must emit entries.
- Evidence photos live in a private S3-compatible bucket (`EvidencePhoto` rows: `makerspace`,
  `evidence_type`, `object_key`, `uploaded_by`, `created_at`). Workflow records link to these rows.
- Evidence upload uses presigned upload with exact MIME binding + content-length range
  (`EVIDENCE_ALLOWED_MIME`). Upload/detail URLs are scoped by per-makerspace `UPLOAD_EVIDENCE` + active
  status (not global roles — membership-only Inventory Managers can upload/view in their makerspace).
- `AWS_S3_ENDPOINT_URL` = backend-facing; `AWS_S3_PUBLIC_ENDPOINT_URL` = browser-facing presigned URLs
  (dockerized backend needs `http://minio:9000` vs `http://localhost:9000`).
- Object keys are identifiers, not secrets — privacy is the private bucket + short-lived signed URLs.

## Learning And Explanation Contract

This repo is also being used to learn production Django, DRF, React, and TanStack Query through the inventory manager project. When making changes:

- Explain the reason for each meaningful change in plain language.
- Keep explanations brief but logically deep enough to show the production tradeoff.
- For small diffs, explicitly state what changed, why it changed, and what behavior it protects.
- Tie backend changes back to Django/DRF concepts such as models, serializers, viewsets/APIViews, permissions, transactions, migrations, and service modules.
- Tie frontend changes back to React/TanStack Query concepts such as component state, server state, query keys, mutations, invalidation, loading/error states, and cache refresh.
- Avoid unexplained "magic" abstractions. If an abstraction is introduced, explain the repeated problem it removes.
- Prefer teaching through this project's real workflows: request creation, accept/reject, issue, return, QR scan, evidence upload, and audit log.

The goal is not just to ship code, but to understand why each production-quality decision exists.

## Engineering Conventions (apply to all code written here)

- **Follow the global Claude config.** The gated workflow in `~/.claude/CLAUDE.md` (Stages 1–6, Codex delegation, mandatory review/QA gates) governs all work in this repo. Repo-specific rules below add to it; they do not override it.
- **Document every API endpoint in Swagger / OpenAPI.** Every route in the API surface (PRD §14) must have an OpenAPI spec entry — request/response schemas, auth requirements, and error responses. Keep the spec in sync with the code; an undocumented endpoint is incomplete.
- **Keep files modular — target ~200 lines per file, hard ceiling ~300.** One clear responsibility per file. When a module file grows past the target, split it (e.g. route handlers, validation, and service logic in separate files). The deep modules in §12 are logical boundaries, not single files. **Established split pattern:** when an app's `views.py`/`serializers.py`/`admin.py`/`services.py` outgrows the ceiling, split classes/functions into domain submodules (`views_*`, `serializers_*`, `admin_*`, `services_*`) and keep the original file as a **thin re-export barrel** (explicit `from .submodule import (...)`, never `import *`) so `from app.views import X` and `views.X` keep resolving; for `admin.py` the barrel must still import the admin submodules so the `@admin.register` side effects fire. Every backend code file is within the ceiling **except `backend/config/settings.py`** — Django settings are conventionally a single file (accepted exception).
- **Production-level code, not prototype code.** Validate all inputs at the boundary, handle external-service failure explicitly (especially the Check-In API — fail safe, never crash a request flow), use structured logging, return consistent typed error responses, and never leave `TODO`/stub auth or scoping in a merged path. Every state-changing endpoint must emit its audit log entry (PRD §11). Honor the immutability/append-only and makerspace-scoping invariants already documented above as enforced code, not convention.

## What This System Is

A multi-tenant system for managing community hardware loans across makerspaces. The central concern is **traceability of physical handovers**: every issue and return must produce evidence (QR scans + photos + remarks + audit log) so that accountability for lost/damaged hardware is never ambiguous. Public users browse and request; when self-checkout is enabled they may also issue/return eligible QR tools after Check-In verification and evidence upload. Staff physically issue reviewed requests and direct handouts according to action scope.

## Architecture: Concepts That Span Multiple Modules

The PRD specifies a layered design where UIs and the Telegram bot are thin clients over an API server composed of deep modules. Two architectural rules are load-bearing and easy to violate if you only read one module:

1. **The Request Workflow Module is the single source of truth for state transitions.** Telegram callbacks, the web admin panel, and the guest-admin app must all route through the *same* workflow service — never mutate `HardwareRequest.status` directly. The Telegram module in particular must call the workflow module, not the database. This is what keeps web and bot behavior consistent and audited.

2. **The Inventory Availability Module owns all quantity math.** Reserve / issue / return / mark-lost all flow through it. No other module computes available/reserved/issued counts. The invariant "availability never goes below zero" lives here.

### Module responsibilities

- **Auth & RBAC** — enforces the role/action matrix AND makerspace scoping on every query. Super Admin is global; Space Manager, Inventory Manager, Guest Admin, Print Manager, Machine Manager are per-makerspace memberships (now resolved via editable custom roles, action-based). Inventory Manager is membership-only and covers the full hardware lifecycle but not printing, staff, or makerspace settings. Also verifies Telegram actors and blocks restricted/suspended users. Interface: `can(actor, action, resource)`, `scope_by_makerspace(actor, query)`, `assertTelegramActorCan(...)`.
- **Request Workflow** — owns the state machine, emits audit logs, triggers Telegram alerts, coordinates inventory reservation/issue/return.
- **Inventory Availability** — quantity math + asset status for QR-tracked tools.
- **QR Code & Box** — generates/resolves/revokes QR codes, assigns boxes to requests, tracks scan history.
- **Evidence Photo** — immutable issue/return photo storage linked to actor + request + QR scans; object storage, never public.
- **Check-In API Client** — wraps the external check-in service that verifies requesters and returns `username`. Must fail safely if that API is down.
- **Telegram Integration** — sends per-makerspace group alerts and processes accept/reject callbacks (delegating to Request Workflow).

## Request State Machine

```
draft → pending_approval → {rejected | accepted}
accepted → issued → {partially_returned | returned | closed_with_issue}
```

The workflow module enforces *allowed* transitions only. `closed_with_issue` and the accountability/access-restriction flow (PRD §6.5) are how lost/damaged hardware ties back to a requester's `access_status`.

## Multi-Tenancy (Makerspace Scoping)

Every domain entity is scoped to a `makerspace_id`. A makerspace owns its inventory, public URL, Space Managers, Inventory Managers, Guest Admins, Telegram group chat ID, QR namespace, and audit-log scope. **Any list/query for makerspace-scoped staff actors must be scoped through the Auth module** — forgetting this is a cross-tenant data leak, not just a bug.

## Hard Rules Baked Into Workflows (don't regress these)

- Reviewed-request hardware **cannot be issued** without both a box QR scan and an issue photo.
- Public self-checkout and staff direct handout **cannot be issued** without uploaded issue evidence and an eligible scanned/selected tool.
- Hardware **cannot be returned** without a return photo and a return remark/notes.
- Issued quantity cannot exceed accepted quantity without authorized workflow permission.
- Guest Admins can issue accepted requests and process scoped returns through the same evidence/QR/remark/audit workflow as staff. They **cannot** accept/reject, edit inventory, manage QR, or create direct handouts. Direct handouts (a loan with no reviewed request) require the dedicated `ISSUE_DIRECT_LOAN` action, granted only to Space Manager + Inventory Manager.
- Public request lookup verifies the identifier through Check-In and scopes results to that verified identity — it never matches free-text contact fields (no enumeration by known email/phone).
- Inventory Managers can run the full hardware lifecycle but **cannot** manage printing, staff, or makerspace settings.
- Evidence endpoints require per-makerspace `UPLOAD_EVIDENCE` plus active status; QR management also checks active status.
- Evidence photos and QR scan records are **immutable**; audit logs are **append-only**.
- Public inventory must never expose: storage locations, box IDs, QR codes, scan history, evidence photos, requester history, or hidden counts. Public visibility is governed per-item by `is_public`, `show_public_count`, and `public_availability_mode` (`exact_count | status_only | hidden`).

## Key References in the PRD

- Roles & permission matrix: §4
- Core workflows (request → accept → issue → return → restrict): §6
- Data model (entities + fields): §13
- API surface (public / auth / admin / guest-admin / telegram routes): §14
- App/dashboard navigation tree: §15
- MVP vs. later scope: §16
- Behaviors that must be tested: §17 (test external behavior, not implementation)
- Unresolved decisions: §18 — **resolve relevant open questions before implementing the affected area** rather than guessing.
