# AGENTS.md

Cross-agent instructions for any AI coding tool working in this repo (Codex / GPT-5.5,
Gemini, Copilot, Claude, etc.). **`CLAUDE.md` is the full, authoritative project guide** —
read it for architecture, the current source map, and the recent-change log. This file
inlines the rules that must never be violated, so a tool that reads only `AGENTS.md` stays safe.

## What this system is

A multi-tenant system for managing community hardware loans + 3D printing across makerspaces.
The central concern is **traceability of physical handovers**: every issue/return must produce
evidence (QR scans + photos + remarks + audit log). Public users browse and request; only
authorized staff physically issue items.

## Stack

- **Backend:** Django 5 + Django REST Framework (`backend/`)
- **Frontend:** React 18 + Vite 5 + TypeScript (`frontend/`), TanStack Query v5
- **DB:** PostgreSQL 16 (Docker `docker-compose.yml`)
- **Object storage:** MinIO (self-hosted, S3-compatible) — `AWS_*` names are just the S3 protocol
- **API docs:** drf-spectacular / OpenAPI; **Admin theme:** django-unfold (mounted at `/control/`)

## Load-bearing architectural rules (do not violate)

1. **Request Workflow is the single source of truth for state transitions.** Telegram callbacks,
   the web admin, and guest-admin must all route through `apps/hardware_requests/workflow.py` /
   `apps/printing/workflow.py` — never mutate `*.status` directly.
2. **Inventory Availability owns all quantity math.** Reserve/issue/return/mark-lost flow through
   `apps/inventory/availability.py`. No other module computes available/reserved/issued counts.
   Invariant: availability never goes below zero.
3. **Makerspace scoping on every staff query.** Every domain entity is scoped to `makerspace_id`.
   Any list/query for makerspace-scoped staff actors MUST go through `apps/accounts/rbac.py`
   (`can`, `scope_by_action`, `makerspaces_for_action`). Forgetting this is a cross-tenant data
   leak, not just a bug.
4. **Audit logs are append-only; evidence photos and QR scan records are immutable.** Enforced in
   model methods AND by Postgres triggers. Every state-changing endpoint emits an audit entry via
   `apps.audit.services.record(...)`.
5. **Superadmin control plane is `/control/` (Django admin), superadmin-only**, and is NOT proxied
   on the public frontend port (`frontend/nginx.conf`). The React staff console lives at `/admin`.

## Hard workflow rules

- Hardware cannot be issued without **both** a box QR scan and an issue photo.
- Hardware cannot be returned without a return photo **and** a return remark.
- Issued quantity cannot exceed accepted quantity without authorized workflow permission.
- Public inventory must never expose: storage locations, box IDs, QR codes, scan history, evidence
  photos, requester history, or hidden counts.
- Per-makerspace secrets (`telegram_bot_token`, `smtp_password`) are encrypted at rest with
  `API_CLIENT_ENC_KEY` (Fernet) and decrypted only in delivery code. Serializers expose them
  write-only + a `*_set` boolean — never return the value.
- The Check-In API client must **fail safe** (`CheckinUnavailable`→503), never crash a request flow.

## Engineering conventions

- **Production-level code, not prototypes.** Validate inputs at the boundary, handle external-service
  failure explicitly, return consistent typed error responses, emit the audit log entry. No stub
  auth/scoping in a merged path.
- **Document every API endpoint in OpenAPI** (`@extend_schema`). Keep `frontend/openapi-schema.json`
  + the generated `frontend/src/generated/api.ts` in sync.
- **Keep files modular — target ~200 lines, hard ceiling ~300.** When `views.py`/`serializers.py`/
  `admin.py`/`services.py` outgrows the ceiling, split into domain submodules (`views_*`, etc.) and
  keep the original as a thin re-export barrel (explicit imports, never `import *`). Accepted
  exception: `backend/config/settings.py`.
- **Minimum code that solves the problem.** No speculative abstractions, no unrequested
  configurability, no error handling for impossible scenarios. Every changed line should trace to the
  request.

## Deployment modes (env-toggled)

The backend runs self-hosted (local Postgres + MinIO) by default, or on **managed platforms**
(Supabase free tier) via env vars that all default to the self-hosted behavior — see
`docs/supabase-deployment.md`. Toggles: `MANAGED_POSTGRES` (purge GUC vs `session_replication_role`),
`STORAGE_PRESIGN_METHOD` (`post` MinIO ↔ `put` Supabase Storage), `CONN_MAX_AGE` /
`DISABLE_SERVER_SIDE_CURSORS` (transaction pooler), `CRON_SECRET` (enables the fail-closed
`POST /api/v1/internal/cron/return-reminders` endpoint). **Do not change these defaults** — they
keep localhost identical; only managed deployments set them.

## Local development

```bash
docker compose up -d db                     # 1. Database
cd backend && pip install -r requirements.txt
python manage.py migrate && python manage.py seed_demo
python manage.py runserver                  # http://localhost:8000  (Swagger: /docs/, ReDoc: /redoc/, schema: /schema/)
cd frontend && npm install && npm run dev   # http://localhost:5000
cd backend && pytest                        # tests (DB must be up)
```

## Source map (start here)

- `backend/config/` — Django project (`settings.py`, `urls.py`). All API routes under `/api/`.
- `backend/apps/accounts/rbac.py` — Auth & RBAC: `can`, `scope_by_action`, makerspace scoping.
- `backend/apps/makerspaces/` — `Makerspace` tenant root, `frontend_domain`, bootstrap, module flags.
- `backend/apps/hardware_requests/workflow.py` — request state machine (single source of truth).
- `backend/apps/inventory/availability.py` — quantity math (single source of truth).
- `backend/apps/printing/` — 3D printing lifecycle (`workflow.py`, public + managed surfaces).
- `backend/apps/audit/`, `backend/apps/evidence/`, `backend/apps/boxes/` — append-only/immutable records.
- `backend/tests/` — pytest behavior tests (test external behavior, not implementation).
- `frontend/src/features/` — `inventory/` (public) and `staff/` (admin console) feature slices.

## Tests

Run `cd backend && pytest` (Postgres must be up). Test **external behavior, not implementation**.
The suite is the gate — do not leave it red.
