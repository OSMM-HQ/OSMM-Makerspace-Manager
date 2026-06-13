# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

**Implementation is in progress.** Public inventory browse, staff auth/RBAC foundations,
API-client HMAC support, QR/box foundations, Phase 3 audit/evidence
infrastructure, the 3D Printing Manager (request lifecycle + email
notifications), and the Hardware Request Workflow (public submission + admin
accept/reject plus issue/handover, with check-in seam, reserve-at-acceptance, box
scan, issue-photo attach, return processing/accountability, and stock movement
through reserved/issued/returned/damaged/lost buckets) are in place. The QR/asset
module, admin REST surface, access-restriction endpoints, Telegram webhook/test
alert integration, publishable-key public API hardening, and first-pass Space
Manager (`/admin`) / Guest Admin frontend are also in place.
Hardware request emails are template-backed through Django admin
(`HardwareEmailTemplate`), accepted/issued/returned/rejected/request-received
emails use those templates with safe defaults, and return reminders are sent by
the `send_return_reminders` management command for overdue active loans.

The multi-frontend platform and open-source operations/reporting PRDs now have
their in-scope requirements implemented end-to-end. Items the PRDs explicitly
exclude or defer, such as procurement, maintenance, direct Google Sheets OAuth
publishing, native apps, and physical label-printer control, remain future work
rather than current implementation gaps.

Implemented from `docs/prd-multifrontend-platform.md`:

- `TenantFrontend` registry with explicit frontend types, active/primary flags,
  hostnames, allowed origins, module overrides, theme config, and branding config.
- Anonymous-safe `GET /api/v1/bootstrap` that resolves by tenant token, public
  code, slug, hostname, or registered origin and returns only frontend-safe
  makerspace/client configuration.
- Per-makerspace module flags, theme settings, and branding fields on
  `Makerspace`.
- Dynamic CORS signal that allows registered makerspace/frontend origins in
  addition to static settings.
- Admin REST endpoints for listing/creating/updating registered tenant frontends.
- Module guards across public, staff, guest-admin, printing, integrations,
  QR/scanner, reporting, stocktake, transfer, container, and setup workflows.
- Frontend public catalog bootstraps tenant branding/modules at runtime.
- Browser HMAC secret usage was removed from the frontend contract; browser
  clients use publishable/bootstrap configuration only.
- API-client browser/server type, scope metadata, rate-limit tier metadata, and
  scope enforcement for protected API traffic.
- Generated TypeScript API client from OpenAPI
  (`frontend/scripts/generate-api-client.mjs`, `frontend/src/generated/api.ts`).
- Dedicated frontend routes for public catalog, public item detail, kiosk,
  scanner, staff admin, guest admin, and superadmin surfaces.
- Scanner QR resolve endpoint with immutable scan events and allowed-action
  responses for box/product/asset/request QR payloads.

Implemented from `docs/prd-open-source-ops-and-reporting.md`:

- `GET /api/v1/health/` and `GET /api/v1/health/readiness/`.
- `setup_instance` management command for first superadmin and first makerspace.
- Production-image Compose file (`docker-compose.prod.yml`), root `.env.example`,
  Docker health checks, and `docs/self-hosting.md`.
- Staff refresh lifetime is 7 days in SimpleJWT settings.
- Telegram request notifications include requester contact fields,
  `requested_for`, and requested item lines.
- Guest admins can process returns for scoped makerspaces through the same
  audited return workflow as staff.
- `apps.operations` with stock transfers, stocktake sessions/lines,
  inventory adjustments, analytics summaries, CSV/XLSX exports, QR print
  batches, print-ready batch HTML, container APIs, and bulk asset QR generation.
- First-pass admin frontend panels for transfers, stocktake, reports, QR batches,
  compact operations navigation, saved local inventory views, inline details,
  and bulk public QR enable/disable actions.
- Light theme is now default with a persistent dark theme toggle.
- Docker image publishing workflow for GHCR
  (`.github/workflows/docker-images.yml`).
- Public item detail pages backed by a safe public detail API.
- Serialized direct handout enforcement: individual-mode products require a
  scanned asset QR payload; quantity-mode direct handout remains supported.
- Direct Google Sheets publishing, procurement, maintenance, native apps, and
  direct label-printer integrations remain out of scope or future work per the
  PRDs.

Stack (in use):

- **Backend:** Django 5 + Django REST Framework (`backend/`)
- **Frontend:** React 18 + Vite 5 + TypeScript (`frontend/`)
- **Server-state management:** TanStack Query v5
- **Database:** PostgreSQL 16 (via `docker-compose.yml`)
- **Styling:** Tailwind CSS 3 with CSS-variable light/dark theme tokens. Light
  is the default; the frontend persists the user's dark-theme toggle locally.
- **API documentation:** drf-spectacular / OpenAPI
- **Admin theme:** Django admin themed with django-unfold (dark + purple, forced dark); site name configurable via `ADMIN_SITE_NAME` (default "Makerspace Inventory")
- **Telegram integration:** implemented for request alerts, test alerts, and
  authenticated webhook accept/reject callbacks.

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

- Public inventory page: `http://localhost:5000/m/tinkerspace`
- API: `http://localhost:8000/api` — Swagger docs at `http://localhost:8000/api/docs/`, schema at `/api/schema/`.

### Current source map (real paths)

- `backend/config/` — Django project (`settings.py`, `urls.py`, wsgi/asgi). All API routes mounted under `/api/`.
- `backend/apps/accounts/` - custom `User` model (`AUTH_USER_MODEL`), JWT auth views, and `rbac.py` (the Auth & RBAC module: `can(...)`, action-scoped `makerspaces_for_action`/`scope_by_action`, makerspace scoping).
- `backend/apps/makerspaces/` — `Makerspace` model (tenant root; unique `slug`),
  `TenantFrontend` registry, tenant bootstrap views, dynamic CORS registration,
  module flags, module guards, and frontend-safe platform helpers.
- `backend/apps/audit/` - append-only `AuditLog` plus `audit.record(...)`.
- `backend/apps/evidence/` - immutable evidence photo rows, S3-compatible storage
  helpers, and signed upload/view URL endpoints gated by per-makerspace
  `UPLOAD_EVIDENCE` permission plus active account status.
- `backend/apps/boxes/` - Box QR payloads plus immutable `BoxScan` records for
  issue/return scan history, generalized `QrCode`, and immutable `QrScanEvent`
  records for box/product/asset/scanner lookup scans.
- `backend/apps/admin_api/` - staff REST surface for makerspaces, inventory CRUD,
  bulk inventory import preview/apply, staff membership management
  (`users/space-managers`, `users/inventory-managers`, `users/guest-admins`,
  `users/print-managers`), tenant frontend registry management, user
  restrict/restore, scoped API-client issuance, and audit-log reads.
- `backend/apps/operations/` - open-source ops/reporting slice: health checks,
  stock transfers, stocktake, inventory adjustments, analytics, CSV/XLSX report
  exports, container/location APIs, QR print batches, print-ready QR batch HTML,
  and serialized asset QR generation.
- `backend/apps/integrations/` - Telegram message delivery, webhook callback
  routing through the hardware request workflow, and test-alert endpoint. The
  webhook authenticates Telegram's `X-Telegram-Bot-Api-Secret-Token` header
  against `TELEGRAM_WEBHOOK_SECRET` (fail-closed when unset) before trusting the
  attacker-controllable `from.id`; only then does it route accept/reject.
  Telegram group chat IDs are configuration, not secrets; makerspace Telegram
  bot tokens and SMTP passwords are encrypted at rest with `API_CLIENT_ENC_KEY`
  and are only decrypted inside delivery code.
- `backend/apps/hardware_requests/workflow.py` now also owns `assign_box` and
  `issue_request`/`return_items`; `views.py` exposes admin active-loans,
  assign-box, issue, and return endpoints with 404-before-403 scoping.
- `backend/apps/inventory/availability.py` owns `reserve_for_request`,
  `issue_items`/`return_items`, plus `issue_available`/`return_to_available` (the
  no-reservation available↔issued path used by public self-checkout and admin
  direct handout); it is the only place
  available/reserved/issued/damaged/lost counts change.
- `backend/apps/inventory/` — `InventoryProduct` and `InventoryAsset` models, `public_availability.py` (availability service — seeds the Inventory Availability Module), `serializers.py` (allowlist-only public serializer), `views.py` (`PublicInventoryListView`, `PublicInventoryDetailView`), `urls.py`, `management/commands/seed_demo.py`.
- `backend/apps/printing/` — 3D Printing Manager: `PrintBucket`/`PrintRequest`,
  `PrintPrinter`, and `FilamentSpool` models; print managers can add scoped
  printers/spools, assign printer + spool + slicer estimates when a request
  starts, and see free/busy printer state, pending estimated minutes, and
  estimated spool remaining after the queued work. `workflow.py` remains the
  single source of truth for request transitions (row-locked + audited);
  `permissions.py` provides `CanManagePrinting` action-aware 403/404; `emails.py`
  sends fail-safe branded SMTP notifications. Templates in
  `backend/templates/email/`.
- `backend/apps/hardware_requests/` — Hardware Request Workflow (submit + accept/reject + issue + return): `HardwareRequest`/`HardwareRequestItem`, immutable `ReturnEvent`, and immutable `RequesterAccountability` models; `workflow.py` (single source of truth: `submit_request`/`accept_request`/`reject_request`/`assign_box`/`issue_request`/`return_items`, atomic + row-locked + audited; reserve-at-acceptance); `permissions.py` (`CanReviewRequest`, `CanViewHandoverQueue`, `CanReturnRequest`); `serializers.py` (strict public-status allowlist plus return item resolutions); `views.py` (public submit/verify/status under HMAC-protected `public/`; admin queues + accept/reject/assign-box/issue/return with 404-before-403 scoping); `exceptions.py` (workflow→HTTP exception handler + `ErrorSerializer`); `notifications.py` (Telegram seam); `urls.py`, `admin.py`.
- `backend/apps/hardware_requests/management/commands/send_return_reminders.py`
  — scheduled email reminder job. Run from cron/Task Scheduler; it only sends
  for issued/partially-returned requests whose `return_due_at` is past and whose
  reminder has not already been sent.
- `backend/apps/checkin/` — fail-closed Check-In API client (`client.py`: `verify()`, `CheckinUnavailable`→503 / `CheckinDenied`→403; `stub` vs `http` backend via `CHECKIN_MODE`, http-mode config validated at boot).
- `backend/apps/inventory/availability.py` — Inventory Availability quantity math (`reserve_for_request`, `issue_items`, `return_items`, plus the no-reservation `issue_available`/`return_to_available` helpers; row-locked, never-below-zero, `InsufficientStock`). The only place reserve/available/issued/damaged/lost counts change — the self-checkout and direct-loan workflows delegate their stock mutations here rather than open-coding them.
- `backend/tests/` — pytest behavior tests (public endpoint, auth/RBAC, audit/evidence, printing).
- `frontend/openapi-schema.json`, `frontend/scripts/generate-api-client.mjs`, and
  `frontend/src/generated/api.ts` - checked-in OpenAPI snapshot and generated
  TypeScript API path/client metadata.
- `frontend/src/features/inventory/` — `PublicInventoryPage`,
  `PublicItemDetailPage`, `ProductCard`, `AvailabilityBadge`, query hook + API
  client.
- `frontend/src/features/staff/` - first-pass Space Manager and Guest Admin panels:
  login, request queues, handover/return actions, inventory table, stock
  transfers, stocktake, reports/exports, bulk import preview/apply, QR tools,
  API clients, users, audit logs, scanner/kiosk/superadmin route surfaces, saved
  local inventory views, inline details, and bulk inventory actions.
- `frontend/src/lib/`, `frontend/src/components/ui/`, `frontend/src/types/` — query client, fetch wrapper, themed primitives, shared types.

### Public availability rule (resolves PRD §5's two overlapping fields)

`public_availability_mode` is the master display switch; `show_public_count` is a safety gate for exact counts:

- `is_public = false` → product excluded from the public list entirely.
- mode `hidden` → product listed, `availability: null`.
- mode `status_only` → `{ mode: "status_only", label }`.
- mode `exact_count` → exact `count` **only if** `show_public_count = true`; otherwise falls back to `status_only`.
- Status label: `available ≤ 0` or `total ≤ 0` → `Unavailable`; `available ≤ ceil(total × 0.2)` → `Limited`; else `Available`.

The API response is DRF-paginated (`PageNumberPagination`, page size 24): `{ count, next, previous, results }`. This is the standing convention for all list endpoints.

### Phase 3 audit + evidence conventions

- Audit writes go through `apps.audit.services.record(actor, action, ...)`.
  `AuditLog` is append-only in model methods and by Postgres triggers; later
  workflow phases must emit entries from their state-changing services.
- Evidence photos live in a private S3-compatible bucket. The DB stores
  `EvidencePhoto` rows with `makerspace`, `evidence_type`, `object_key`,
  `uploaded_by`, and `created_at`; request/workflow records will link to these
  rows in later phases, not the other way around.
- Evidence upload uses presigned POST, not PUT, with exact MIME binding and a
  content-length range. Supported MIME types are configured by
  `EVIDENCE_ALLOWED_MIME`.
- Evidence upload and detail URLs are scoped by the actor's per-makerspace
  `UPLOAD_EVIDENCE` action and require active account status. They do not rely
  on global staff roles, so membership-only Inventory Managers can upload/view
  evidence in their assigned makerspace.
- `AWS_S3_ENDPOINT_URL` is the backend-facing endpoint. `AWS_S3_PUBLIC_ENDPOINT_URL`
  is used for browser-facing presigned URLs. Host dev defaults both to
  `http://localhost:9000`; a dockerized backend will need the internal/public
  split (`http://minio:9000` vs `http://localhost:9000`).
- Object keys are identifiers, not secrets. Privacy is enforced by the private
  bucket and short-lived signed URLs, not by hiding object-key values.
- A presigned POST can overwrite the same object key until it expires. This is
  an accepted Phase 3 risk; Phase 6 attach logic will record the object ETag so
  later byte changes are detectable.

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
- **Keep files modular — target ~200 lines per file, hard ceiling ~300.** One clear responsibility per file. When a module file grows past the target, split it (e.g. route handlers, validation, and service logic in separate files). The deep modules in §12 are logical boundaries, not single files.
- **Production-level code, not prototype code.** Validate all inputs at the boundary, handle external-service failure explicitly (especially the Check-In API — fail safe, never crash a request flow), use structured logging, return consistent typed error responses, and never leave `TODO`/stub auth or scoping in a merged path. Every state-changing endpoint must emit its audit log entry (PRD §11). Honor the immutability/append-only and makerspace-scoping invariants already documented below as enforced code, not convention.

## What This System Is

A multi-tenant system for managing community hardware loans across makerspaces. The central concern is **traceability of physical handovers**: every issue and return must produce evidence (QR scans + photos + remarks + audit log) so that accountability for lost/damaged hardware is never ambiguous. Public users browse and request; only authorized staff (Space Manager, Inventory Manager, Guest Admin, or Super Admin according to action scope) physically issue items.

## Architecture: Concepts That Span Multiple Modules

The PRD specifies a layered design where UIs and the Telegram bot are thin clients over an API server composed of deep modules. Two architectural rules are load-bearing and easy to violate if you only read one module:

1. **The Request Workflow Module is the single source of truth for state transitions.** Telegram callbacks, the web admin panel, and the guest-admin app must all route through the *same* workflow service — never mutate `HardwareRequest.status` directly. The Telegram module in particular must call the workflow module, not the database. This is what keeps web and bot behavior consistent and audited.

2. **The Inventory Availability Module owns all quantity math.** Reserve / issue / return / mark-lost all flow through it. No other module computes available/reserved/issued counts. The invariant "availability never goes below zero" lives here.

### Module responsibilities (conceptual — no files exist yet)

- **Auth & RBAC** - enforces the role/action matrix AND makerspace scoping on every query. Super Admin is global; Space Manager, Inventory Manager, Guest Admin, and Print Manager are per-makerspace memberships. Inventory Manager is membership-only and covers the full hardware lifecycle (`view/edit_inventory`, accept/reject, assign box, issue, return, upload evidence, manage QR, view audit) but not printing, staff, or makerspace settings. Also verifies Telegram actors before bot actions and blocks restricted/suspended users. Interface: `can(actor, action, resource)`, `scopeByMakerspace(actor, query)`, `assertTelegramActorCan(...)`.
- **Request Workflow** — owns the state machine, emits audit logs, triggers Telegram alerts, coordinates inventory reservation/issue/return.
- **Inventory Availability** — quantity math + asset status for QR-tracked tools.
- **QR Code & Box** — generates/resolves/revokes QR codes, assigns boxes to requests, tracks scan history.
- **Evidence Photo** — immutable issue/return photo storage linked to actor + request + QR scans; lives in object storage, never public.
- **Check-In API Client** — wraps the external check-in service that verifies requesters and returns `username`. Must fail safely if that API is down. The exact request/response shape is an open question (PRD §18).
- **Telegram Integration** — sends per-makerspace group alerts and processes accept/reject callbacks (delegating to Request Workflow).

## Request State Machine

```
draft → pending_approval → {rejected | accepted}
accepted → issued → {partially_returned | returned | closed_with_issue}
```

The workflow module enforces *allowed* transitions only. `closed_with_issue` and the accountability/access-restriction flow (PRD §6.5) are how lost/damaged hardware ties back to a requester's `access_status`.

## Multi-Tenancy (Makerspace Scoping)

Every domain entity is scoped to a `makerspace_id`. A makerspace owns its inventory, public URL, Space Managers, Inventory Managers, Guest Admins, Telegram group chat ID, QR namespace, and audit-log scope. **Any list/query for makerspace-scoped staff actors must be scoped through the Auth module** - forgetting this is a cross-tenant data leak, not just a bug.

## Hard Rules Baked Into Workflows (don't regress these)

- Hardware **cannot be issued** without both a box QR scan and an issue photo.
- Hardware **cannot be returned** without a return photo and a return remark.
- Issued quantity cannot exceed accepted quantity without authorized workflow permission.
- Guest Admins can issue accepted requests and process scoped returns through the
  same evidence/QR/remark/audit workflow as staff. They **cannot** accept/reject,
  edit inventory, manage QR, or create direct handouts. Direct handouts (a loan
  with no reviewed request) require the dedicated `ISSUE_DIRECT_LOAN` action,
  granted only to Space Manager + Inventory Manager.
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
