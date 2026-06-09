# 3D Printing Manager — Design Spec

**Date:** 2026-06-09
**Status:** Approved (design); pending implementation plan
**App:** `backend/apps/printing/` (new)

## Purpose

Let makerspace members request 3D prints, organize those requests into
local-DB **buckets** (logical queues), and give a dedicated **print-manager**
account the ability to triage them through a full lifecycle. Status changes
emit audit entries and send branded HTML emails to the requester over SMTP.
The system exposes a total list of completed ("printed") jobs.

This is a self-contained domain alongside the (future) hardware-request
workflow. It reuses existing infrastructure: Phase 2 auth/RBAC + makerspace
scoping, and the Phase 3 `apps.audit.record()` service.

## Decisions (from brainstorming)

- **Role:** new per-makerspace `print_manager` role on `MakerspaceMembership.Role`
  — not a 5th global `User.Role`. A print-manager is a `User` with a
  `MakerspaceMembership(role=print_manager)`, authenticating through Phase 2 auth.
- **Buckets:** logical groupings in Postgres (no S3 / object storage).
- **Lifecycle:** full state machine (`pending → accepted → printing → completed`,
  plus `rejected` and `failed` terminal branches).
- **Email:** SMTP, HTML body with a shared branded header partial. Triggers on
  **accept**, **reject**, and **completion** — all to the requester.
- **No file upload:** requesters provide a `source_link` URL to their model.
- **Bucket selection:** requester picks an active bucket at creation time;
  buckets are pre-defined per makerspace by admins/managers.

## RBAC

Add `PRINT_MANAGER = "print_manager"` to `MakerspaceMembership.Role`.

Permission rules (enforced in the Phase 2 RBAC layer, makerspace-scoped):

| Action | requester | print_manager | admin | superadmin |
|---|---|---|---|---|
| Create print request (active access only) | ✅ | — | — | — |
| List/view own requests | ✅ | — | — | — |
| List/manage requests in makerspace | — | ✅ (own ms) | ✅ (own ms) | ✅ (all) |
| Accept / reject / start / complete / fail | — | ✅ (own ms) | ✅ (own ms) | ✅ (all) |
| List buckets (read) | ✅ | ✅ (own ms) | ✅ (own ms) | ✅ (all) |
| Create/edit buckets (Django admin) | — | — | ✅ (own ms) | ✅ (all) |

A `print_manager` membership grants **only** printing actions — not inventory
edit, QR, or hardware-request approval. Requesters with `access_status` of
`restricted`/`suspended` are blocked from creating requests.

## Data model (Postgres)

### `PrintBucket`
- `makerspace` FK → Makerspace (CASCADE)
- `name` CharField
- `description` TextField (blank)
- `is_active` Bool (default True)
- `created_at`, `updated_at`
- Unique constraint: `(makerspace, name)`

Logical queue, distinct from the physical `Box` model.

### `PrintRequest`
- `bucket` FK → PrintBucket (PROTECT) — makerspace is derived from the bucket
- `requester` FK → User (PROTECT)
- `title` CharField
- `description` TextField (blank)
- `material` CharField (blank), `color` CharField (blank)
- `quantity` PositiveIntegerField (default 1, min 1)
- `source_link` URLField (blank) — URL to the model file
- `status` CharField choices: `pending|accepted|printing|completed|rejected|failed` (default `pending`)
- `reason` TextField (blank) — populated on reject/fail
- `handled_by` FK → User (SET_NULL, null) — manager who last acted
- `created_at`, `accepted_at` (null), `completed_at` (null), `updated_at`

The bucket's makerspace is the request's tenant; all manager queries are
scoped to it. A convenience `makerspace` property reads `bucket.makerspace`.

## Lifecycle / workflow service

`apps/printing/workflow.py` is the **single source of truth** for status
transitions (mirrors the architectural rule that workflow modules own state).

```
pending  ──accept──▶ accepted ──start──▶ printing ──complete──▶ completed
   │                                          │
   └──reject(reason)──▶ rejected              └──fail(reason)──▶ failed
```

Each transition function (`accept`, `reject`, `start`, `complete`, `fail`):
1. Validates the current status allows the transition; else raises a
   `InvalidTransition` error → API returns **409**.
2. Updates `status`, `handled_by`, and the relevant timestamp inside a
   `transaction.atomic()` block.
3. Writes an audit entry via
   `apps.audit.record(actor, action, makerspace=request.bucket.makerspace, target=request)`
   (keyword args — the real signature is
   `record(actor, action, *, makerspace=None, target=None, ...)`) with actions
   `print.accepted`, `print.rejected`, `print.started`, `print.completed`,
   `print.failed`. Transitions re-fetch with `select_for_update()` under the lock
   to prevent concurrent double-writes.
4. Queues the relevant email via `transaction.on_commit(...)` (see Email).

No view or admin mutates `status` directly.

## Email (SMTP + HTML)

- **Config (new):** `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
  `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL` — all from env,
  with a console backend default for local dev so nothing is required to run.
- **Templates:** `backend/templates/email/base.html` holds the shared branded
  HTML header (TinkerSpace logo + theme colors `#FBB905`/`#111111`). Per-event
  templates extend it: `print_accepted.html`, `print_rejected.html`,
  `print_completed.html`, each with a matching `.txt` plaintext fallback.
- **Send:** `apps/printing/emails.py` renders via `render_to_string` and sends
  `EmailMultiAlternatives` (text + HTML alternative) to the requester's email.
- **Fail-safe:** emails are dispatched in `transaction.on_commit`; any send
  exception is logged (structured) and swallowed — it never rolls back or
  crashes the transition. (Production rule: external-service failure must not
  break the flow.)

## API surface (all under `/api/v1/`, OpenAPI-documented)

**Requester**
- `POST /api/v1/printing/requests/` — create (active requester only)
- `GET  /api/v1/printing/requests/` — list own requests (paginated)
- `GET  /api/v1/printing/requests/{id}/` — view own request
- `GET  /api/v1/printing/buckets/?makerspace=<id>` — active buckets to choose from

**Manager (print_manager / admin / superadmin)**
- `GET  /api/v1/printing/manage/requests/` — scoped list, filter by `status`, `bucket`
- `POST /api/v1/printing/manage/requests/{id}/accept`
- `POST /api/v1/printing/manage/requests/{id}/reject`   (body: `reason`)
- `POST /api/v1/printing/manage/requests/{id}/start`
- `POST /api/v1/printing/manage/requests/{id}/complete`
- `POST /api/v1/printing/manage/requests/{id}/fail`      (body: `reason`)
- `GET  /api/v1/printing/manage/printed/` — **total list of completed prints**,
  scoped by makerspace (superadmin sees all)

**Buckets:** read via the scoped list endpoint above (requesters + managers).
Create/edit/deactivate is **admin/superadmin-only via Django admin (unfold)** in
v1 — print-managers (API-only accounts) manage requests, not buckets. This keeps
the API surface tight; a manager-facing bucket-CRUD API can come later if needed.

All list endpoints use the standing `PageNumberPagination` (page size 24) and
`{ count, next, previous, results }` shape. Cross-tenant access returns 404.

## Requester scoping model (intentional)

This is a public-request system ("public users browse and request"). There is no
requester↔makerspace membership, so **an active requester may create a print
request against any *active* bucket in any makerspace — by design.** Buckets and
makerspaces are treated as public-facing, non-sensitive (bucket names/descriptions
and makerspace IDs are not secrets). To avoid a global listing, the bucket list
endpoint **requires** an explicit `?makerspace=<id>`.

## Error handling

- Invalid transition → **409** with a typed error body.
- Creating against an **inactive** bucket → **400** (other-makerspace active
  buckets are allowed per the model above).
- Bucket list without `?makerspace=`, or an invalid/non-numeric value → **400**.
- Restricted/suspended requester → **403**.
- Cross-tenant manager detail/action (request outside actor's MANAGE_PRINTING
  scope) → **404**.
- Unauthenticated → **401**; authenticated-but-unauthorized → **403**.

## Testing (behavior, not implementation)

- Create / list / view own request; pagination + scoping.
- Each transition: audit row written, email captured — `locmem` backend +
  `captureOnCommitCallbacks(execute=True)` so the `on_commit` dispatch runs;
  correct timestamps/status.
- Invalid transition returns 409 and writes no audit/email.
- Concurrent-transition safety: a second `accept` on an already-accepted request
  returns 409 and does not duplicate audit/email.
- RBAC matrix: requester cannot manage; print_manager can but only in their
  makerspace; admin/superadmin scope; cross-tenant 404.
- **guest_admin** (membership without `MANAGE_PRINTING`): manager list with
  `?makerspace=` omitted returns empty; with their own `?makerspace=` returns 403.
- Requester creating against another makerspace's **active** bucket is allowed;
  against an **inactive** bucket is rejected (400); invalid/non-numeric
  `?makerspace=` returns 400 (not 500).
- Restricted/suspended requester blocked from creating (403).
- Email templates render (subject + HTML header present) for each event.
- `printed/` returns only completed jobs, action-scoped.

## Out of scope (v1)

- File byte uploads (use `source_link`).
- Telegram notifications for prints.
- Printer/asset assignment, cost/time estimation, payment.
- Frontend UI (separate phase).
