# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Recent batch - lean-paid production deploy + perf hardening (2026-06-19)

Added production deployment artifacts for the recommended always-on single-makerspace path:
Supabase Pro Postgres, Render Starter, Cloudflare R2, optional Brevo SMTP, static frontend hosting,
and free cron (`.env.production.example`, `render.yaml`, `docs/deploy-production.md`). This batch
also covers the recent hardening work: composite indexes plus printer/direct-loan/box N+1 fixes,
`email_enabled()` with the `/api/v1/config` gate, and PUT-mode immutable finalize. Worker queues and
automatic immutable-row pruning remain deliberately de-scoped for single-makerspace scale.

## Recent batch — Supabase free-tier dual-mode (env-toggled; localhost default unchanged) (2026-06-19)

Made the backend runnable on **Supabase free tier** (managed Postgres + Supabase Storage) while
keeping the bundled Docker stack (local Postgres superuser + MinIO) behaving **identically by
default** — every switch is an env var defaulting to the current behavior. Codex Stage-1
plan-reviewed (APPROVED after 3 rounds), built in 3 commit-per-green phases (06a2176, 341cab2, +
this). Driven by `docs/performance-and-supabase-report.md` (verdict: free tier = demo/pilot, not
dependable prod; Supabase can't host Django — run it on Render/PythonAnywhere). Operator runbook:
**`docs/supabase-deployment.md`**. New env vars (all default to self-hosted): `MANAGED_POSTGRES`
(False), `STORAGE_PRESIGN_METHOD` (post), `CONN_MAX_AGE` (0), `DISABLE_SERVER_SIDE_CURSORS`
(False), `CRON_SECRET` ("").

- **Purge trigger-suspension (phase 1).** The 5 append-only/immutability reject FUNCTIONS
  (audit/evidence/boxscan/qrscanevent/return-records) were rewritten (migrations audit 0003,
  evidence 0003, boxes 0008, hardware_requests 0014 — **function-body CREATE OR REPLACE only,
  triggers untouched, reverse restores original**) to allow DELETE **only** when the
  transaction-scoped custom GUC `current_setting('app.allow_immutable_delete', true) = 'on'` is
  set; UPDATE stays blocked unconditionally. `lifecycle.py` purge now branches on
  `settings.MANAGED_POSTGRES`: False → `SET LOCAL session_replication_role='replica'` (unchanged
  localhost path, all triggers incl. FK off); True → `SET LOCAL app.allow_immutable_delete='on'`
  (no superuser needed — Supabase forbids `session_replication_role`; only OUR immutability
  triggers are bypassed, FK triggers stay ON, Django collects the graph in dependency order).
  `settings.py` also applies `CONN_MAX_AGE`/`DISABLE_SERVER_SIDE_CURSORS` to `DATABASES["default"]`
  (set both for the Supabase transaction pooler; migrate via the direct/session-pooler URL).
- **Storage presign POST↔PUT (phase 2).** `STORAGE_PRESIGN_METHOD` toggles `evidence.storage`
  + `printing.storage` presign between the legacy `generate_presigned_post` (`post`, MinIO,
  byte-identical response/flow) and `generate_presigned_url("put_object", ...)` (`put`, Supabase).
  POST response shape is **preserved exactly** (the evidence view adds `method`/`headers` only in
  PUT mode; serializer fields are `required=False` so they're omitted under POST). The frontend
  (`EvidenceUpload.tsx`, printing `publicApi.ts`) branches on `method==="PUT"` → `fetch PUT` with
  the **backend-returned** `headers` (not `file.type`, which may be blank). Because PUT loses the
  upload-time `content-length-range`, size is re-validated server-side **PUT-mode-only** at attach
  (`evidence.storage.object_size`; `1 ≤ size ≤ EVIDENCE_MAX_BYTES` in handover/return; printing
  attach now also rejects 0 bytes). **Known PUT-mode limitation** (documented, not fixed — only
  relevant in demo/pilot Supabase mode): the PUT key is overwritable until TTL, so the recorded
  `size_bytes` can drift from the stored object — keep TTLs short + monitor the 1 GB cap.
- **Cron return-reminder endpoint (phase 3).** `send_return_reminders` core extracted to
  `services_return_reminders.run_return_reminders()`; new `POST /api/v1/internal/cron/return-reminders`
  (`cron_views.py`) is `authentication_classes=[]` + no throttle for **deterministic fail-closed
  status**: **404** while `CRON_SECRET` unset, **403** on wrong `X-Cron-Secret` (via
  `secrets.compare_digest`), else runs and returns `{sent, skipped}`. The management command still
  works for manual runs. `docker-compose.yml` + `docker-compose.prod.yml` now pass through all five
  new env toggles. OpenAPI snapshot + generated TS client regenerated.

## Recent batch — one domain per makerspace (replaces TenantFrontend registry) (2026-06-19)

Replaced the per-type `TenantFrontend` frontend registry (7-type dropdown, per-page rows) with a
single **`Makerspace.frontend_domain`** field — "one domain per makerspace, serving all routes."
Codex Stage-1 plan-reviewed (APPROVED after 3 rounds; PRD `docs/prd-single-domain-per-makerspace.md`,
local/gitignored). Built phase-by-phase (commit + full-suite green per phase). Two migrations
(`makerspaces/0015` add fields, `0016` data-migrate hosts, `0017` delete model).

- **Model.** `Makerspace.frontend_domain` (nullable, **case-insensitively unique** via
  `UniqueConstraint(Lower(...))`; `save()` normalizes blank→None + lowercases) + a
  `hidden_from_central_directory` bool with a **DB `CheckConstraint`** (hidden ⇒ domain set) and
  `clean()`. **`TenantFrontend` model + its `/admin/.../frontends` REST endpoints + Django admin are
  DELETED.** Set domain → branded 1:1 site at that domain (all routes: `/`, item/print/checkout,
  `/admin`, `/guest-admin`, `/scanner`); blank → central portal (`/m/<slug>` + shared `/admin`)
  unchanged. Soft-hide drops the space from the central directory (`PublicMakerspaceListView`) only;
  `/m/<slug>` deep link still resolves.
- **Two origin helpers (`platform.py`), staff strict vs public broad.**
  `makerspace_staff_origins` = ONLY `https://<frontend_domain>` (exact, https-only) — feeds
  `staff_origin_is_registered` (refresh/logout CSRF) + `staff_origin_scope` (the origin→tenant
  guard) + `auth_cookies` staff CSRF. `makerspace_public_origins` = that ∪ `cors_allowed_origins` —
  feeds general CORS (`origin_is_registered`) + `FrontendHMACMiddleware` publishable-key validation.
  So an origin only in `cors_allowed_origins` (API-client/public) can make publishable-key calls but
  **can never mint/scope a staff session**. `resolve_frontend`/`bootstrap_payload` now operate on
  `Makerspace` (tenant=`public_code`, origin→`frontend_domain`, or slug); payload shape unchanged
  (`frontend.type` is the constant `"makerspace"`).
- **Isolation (corrected vs the prior "UI-only" claim).** The shipped `origin_scope.py` guard
  hard-scopes a **browser** staff request to its domain's makerspace (acting on another → 403),
  re-pointed here to `frontend_domain`. Origin-less (server-to-server) requests fall back to
  `MakerspaceMembership` (still the underlying authority).
- **Single-tenant frontend (already shipped) reconciliation.** `config.js` still carries
  `tenantToken` (mode detection in `frontend/src/lib/tenant.tsx` unchanged) — its value is now the
  makerspace **`public_code`**, not the deleted `TenantFrontend.token`. Bootstrap-by-origin is an
  additive fallback. The staff console's old "Frontends" tab/panel is removed; the **Custom domain**
  field now lives in `MakerspaceSettingsPanel` (domain input + hide checkbox + URL hint, via the
  makerspace PATCH). OpenAPI snapshot + generated TS client regenerated. Runbooks
  `docs/single-tenant-frontend.md` + `docs/self-hosting.md` updated.

## Recent batch — single-tenant branded frontend (2026-06-17)

Implements the "bring-your-own-site" frontend mode from
`docs/prd-single-tenant-frontend.md`. The same React build now runs in central mode
(unchanged `/m/<slug>` + shared `/admin`) or single-tenant mode when `/config.js`
sets a runtime `tenantToken`.

- Runtime config carries only `apiUrl` + bootstrap tenant token (`TenantFrontend.token`
  or `Makerspace.public_code`). Bootstrap returns the makerspace slug/modules/theme/
  branding and the publishable key; public API calls use that returned key.
- Frontend tenant context is the source of truth for mode, slug, modules, branding,
  and route building. Single-tenant routes are `/`, `/items/:id`, `/print`,
  `/checkout`, `/admin`, `/guest-admin`; central routes stay unchanged.
- Staff access tokens are in memory only. The legacy `makerspace.access` localStorage
  value is deleted on startup/auth cleanup; refresh still uses the httpOnly cookie.
- Single-tenant `/admin` is UI-locked to the configured makerspace and hides switching.
  This is UX only: backend authorization remains `MakerspaceMembership`/RBAC.
- Staff refresh/logout rejects non-localhost `http://` origins before consulting static
  or registered staff origins. Public CORS behavior is unchanged.
- Operator runbook: `docs/single-tenant-frontend.md`.

## Recent batch — superadmin makerspace archive → purge + hard-hide P2 (2026-06-17)

Adds a superadmin-only **two-step makerspace removal** (Codex Stage-1 plan-reviewed: APPROVED after
2 revision rounds; spec `docs/superpowers/specs/2026-06-17-superadmin-archive-purge-makerspace-design.md`).
Surface is the **Django `/control/` admin only** (superadmin-locked by construction). One migration
(`makerspaces/0014`, adds `archived_at`/`archived_by`).

- **Model.** `Makerspace.archived_at` (nullable, indexed; `IS NOT NULL` ⇒ archived — single source
  of truth, no boolean) + `archived_by` (FK user, SET_NULL).
- **Lifecycle service (`apps/makerspaces/lifecycle.py`, single source of truth).** `archive` (atomic
  + `select_for_update`; rejects a hidden `superadmin_access_enabled=False` space and an
  already-archived one; sets `archived_at/by`, flips `public_inventory_enabled=False`; reversible) /
  `unarchive` / `purge`. **Purge is the break-glass op:** guards (archived **and** enabled **and**
  actor `is_superuser`); collects S3 keys (evidence + `PrintRequestFile` + legacy `PrintRequest`
  `model_file`/`estimate_screenshot`/`preview_screenshot`); writes a **platform-scoped**
  (`makerspace=None`) `makerspace.purge_started` audit **before** teardown; in `transaction.atomic()`
  suspends triggers for that transaction only via `SET LOCAL session_replication_role = 'replica'`
  (transaction-scoped: Postgres auto-resets it on commit/rollback/disconnect, so a crash mid-purge can
  never leave the append-only immutability triggers durably disabled platform-wide — `ALTER TABLE …
  DISABLE TRIGGER USER` was rejected because it cannot be re-enabled inside the same transaction that
  modified the table, "pending trigger events", forcing a non-crash-safe post-commit re-enable; the
  lost DB-level FK enforcement is safe because Django's ORM does every CASCADE/SET_NULL fixup in Python
  and the comprehensive test asserts no orphans), then deletes the **full `PROTECT` object graph in a
  verified dependency order** (Django
  `PROTECT` is Python-collector-enforced, so trigger suspension does NOT bypass it — the order must
  clear each `PROTECT` edge before its parent: `QrPrintBatch`→`StockTransfer`(any space-touching, incl.
  cross-makerspace)→stocktake/adjustment→printing→`BoxScan`/`QrScanEvent`/`PublicToolLoan`/return-records
  **before** `HardwareRequest`→`EvidencePhoto`→`QrCode`→assets/products/`Box`→account/api/frontend
  rows→`AuditLog`→`makerspace.delete()`); **after** a clean commit writes `makerspace.purged` and
  best-effort deletes the S3 keys. A surviving cross-makerspace transfer destination keeps its
  `InventoryAdjustment` (transfer `SET_NULL`).
- **Archive = soft-delete for EVERYONE (central rbac, not entry-point-only).** `rbac.archived_makerspace_ids()`
  + exclusion threaded through `resolve_scope`, `makerspaces_for_action(s)`, and (absolute, no member
  carve-out) `can` — so a direct `?makerspace=<archived id>` staff route 403s/empties. Also excluded
  from the superadmin aggregates (`operations.ledger`/`reports`, `printing.reports`, `AuditLogListView`),
  the public bootstrap (`platform.resolve_frontend` + `lookup.py`) + public inventory, the **token-only**
  public status endpoints (`RequestStatusView`, `PublicPrintStatusView`), and the staff makerspace
  switcher + React makerspace list/detail. Archived stays visible **only** in `/control/` for purge.
- **Admin (`apps/makerspaces/admin.py`).** `MakerspaceAdmin.has_delete_permission=False` (kills the
  broken default delete + `delete_selected`); **Archive / Unarchive / Permanently purge** actions, purge
  via an intermediate confirmation page requiring the superadmin to **retype each slug**. Hidden rows are
  already excluded by `SuperuserOnlyModelAdmin._obj_in_hidden`, and the service re-checks
  `superadmin_access_enabled` — so archive/purge can't backdoor the hard-hide governance.
- **Hard-hide P2 fix (carried from the prior batch's Stage-4 review).** `MakerspacePrintingReportView`
  dropped its pre-RBAC `Http404` for a hidden makerspace; the hard block makes `rbac.can()` return False
  → clean **403** (matches the documented status contract). Test renamed
  `test_report_per_makerspace_softhide_404` → `…_hardhide_403`.
- Tests: `backend/tests/test_makerspace_lifecycle.py` (guards; comprehensive populate-every-model purge
  drift-guard incl. `BoxScan/QrScanEvent/PublicToolLoan.request` + cross-makerspace transfer survivor;
  trigger re-enable; archive scope-leak coverage across rbac/aggregates/public/token-status/switcher).

## Recent batch — superadmin access: SOFT hide → HARD block (2026-06-17)

Converted the per-makerspace `superadmin_access_enabled=False` toggle from a SOFT hide (data merely
dropped from aggregate/list surfaces; core RBAC untouched; superadmin kept raw staff-API + Django
`/control/` reach) into a **HARD block**. Codex plan-reviewed (APPROVED after revisions); 508 tests
green. No migration (reuses the existing flag + `PlatformEmailSettings`). **Supersedes the soft-hide
behavior documented in the "collaborative-makerspace self-governance" section below.** NOTE: a hard
block is application-layer only — an instance operator with DB/`manage.py` access can always flip the
flag; that out-of-band override is intentional and undocumented to end users.

- **Centralized RBAC policy (`apps/accounts/rbac.py`).** New `_superadmin_hidden_to_exclude` /
  `_superadmin_visible_ids` / `superadmin_hidden_block_applies` helpers; `can`, `scope_by_action`,
  `scope_by_makerspace`, `makerspaces_for_action`, and `makerspaces_for_actions` now exclude a
  hidden makerspace **for a GLOBAL superadmin** (returns a concrete id set instead of the `ALL`
  sentinel when any makerspace is hidden; `ALL` fast-path preserved when none are). A superadmin who
  holds an EXPLICIT `MakerspaceMembership` in a hidden space keeps that membership ROLE's actions
  only (no global superpower — a hidden-space PRINT_MANAGER ≠ MANAGE_MAKERSPACE). Non-superadmin
  members are unaffected. `hide_from_superadmin` delegates to the same policy (honors the
  explicit-member carve-out), so it can't contradict `scope_by_action`. This single change cascades
  the block to every `/api/v1/admin/...` endpoint and **closes the prior soft-hide
  `?makerspace=<hidden id>` escape hatch** (the audit-report batch's #4) — explicit-id now yields
  403/empty.
- **Existence stays visible (governance/break-glass).** `views_makerspaces.py`: the makerspace
  LIST + detail-GET still return a hidden makerspace to the superadmin as the slim
  `MakerspaceDisabledRowSerializer` (id/name/slug/flag only — no api_key/SMTP/CORS), so it remains
  discoverable; PATCH stays RBAC-scoped, so a superadmin still can't edit/re-enable it (a re-enable
  PATCH now **404s**).
- **Block-OFF-unless-SMTP.** `integrations/email.py` gains `platform_email_configured()`
  (`smtp_host.strip()`); `MakerspaceSerializer` rejects True→False unless the instance Platform
  Email is configured, so locked-out staff always have a forgot-password recovery path. Re-enable
  (False→True) stays space-manager-only (superadmin 400s, or now 404s via the hard block).
- **Break-glass (recovery when all space managers are lost).** `views_users.py`: a superadmin may
  CREATE a brand-new SPACE_MANAGER for a hidden makerspace (`_can_create_staff_role` allows only
  SPACE_MANAGER there; rejects attaching/restoring an EXISTING username/email — fresh account only),
  and may reset a SPACE_MANAGER who manages ONLY hidden makerspace(s) (blocked if they also manage a
  superadmin-access-ENABLED space). Both audited as `superadmin.break_glass_space_manager_created` /
  `..._password_reset`. The created SM logs in and re-enables.
- **Django `/control/` object-level block.** `config/admin_access.py` `SuperuserOnlyModelAdmin` now
  also denies `has_view/change/delete_permission` for a hidden makerspace's row (via `_obj_in_hidden`
  resolving the same `resolve_hidden_lookup` path) — previously only the changelist was filtered, so
  the change/delete PAGES were reachable by id.
- Status contract under the hard block: hidden makerspace → **403** on action/permission-gated
  endpoints (report, managed-print list, …), **404** on object-lookup detail + re-enable PATCH,
  **empty 200** on scope-filtered lists (needs-fix shelf). 404 is no longer used to feign
  non-existence (existence is openly visible as a slim row), so 403 "forbidden" is the honest status.

## Recent batch — audit-report hardening (5 parallel-Codex phases) + lend attribution (2026-06-17)

Fix batch from a 6-Codex codebase audit (Codex plan-reviewed → APPROVED; 5 file-disjoint phases run
as parallel Codex agents, Claude-verified per diff; full suite **498 green**; Codex Stage-4 review =
no actionable issues). One migration (`printing/0010`). Confirmed design decision: the superadmin
soft-hide stays **soft** (per-makerspace report/ledger/lending **404s** kept) — this batch only made
it **consistent**; the SOFT→HARD conversion is a separate queued follow-up (`docs/hard-hide-plan.md`,
not yet built). Commits `a4acab5`,`a95d00f`,`7a8c1ef`,`5cb5e47`,`8f8d7e0`,`9fcc17c` (not pushed).

- **Direct handout via QR no longer requires public flags** (`a4acab5`). `is_public` /
  `public_self_checkout_enabled` gate ANONYMOUS public kiosk eligibility — wrong for a trusted staff
  `ISSUE_DIRECT_LOAN`. `self_checkout_helpers` now threads a keyword-only `require_public=True`
  through `_checkout_target`/`_eligible_product`/`_eligible_asset`/`_checkout_box`; public
  `checkout_tool` keeps `True` (unchanged), staff `issue_direct_loan` passes `False` (same makerspace
  + not archived + available only; box hands out ALL available non-archived contents). Closes the
  "private individual assets have no handout path" gap — staff scan the asset QR. **INDIVIDUAL-tracked
  products are now rejected on the product-QR path AND the box product-contents fallback** (must scan
  the per-unit asset QR; preserves serialized-handout traceability) in BOTH public + staff callers.
  Direct handout also: locks the container `Box` row + wraps `PublicToolLoan.create` in a **nested
  `transaction.atomic()` savepoint** catching `IntegrityError` OUTSIDE it → clean 409 (the outer txn
  stays usable); rejects an **inactive** container; only honors `container_id` when the `containers`
  module is on. `issued_by` ({username, role}) now on the direct-loan serializer + list.
- **QR rebind hardening** (`a95d00f`). Cross-makerspace rebind now requires **both** the SOURCE
  `qr.target_type` AND the destination to be PRODUCT (was only blocking an asset *destination* — an
  asset-origin QR could still cross tenants). The destination-conflict check is `select_for_update`d
  and the `qr.save()` is wrapped in a savepoint → clean 409 (not a 500 from an aborted txn).
  `QrRebindTargetView` gained an explicit `IsActiveStaff`. Frontend: the rebind product picker is
  scoped to the **resolved QR's** makerspace (not the console-selected one), and "Rename & rebind" is
  hidden unless the user holds MANAGE_QR+EDIT_INVENTORY (space/inventory manager or superadmin).
- **Manual print log** (`7a8c1ef`). Mirrors the print-start invariant: re-fetches the printer
  `select_for_update` and rejects `not is_active or status != ACTIVE`; rejects `grams_used <= 0`
  (service guard + `ManualPrintLog` `CheckConstraint`, migration `0010`); fetches printer/spool
  **scoped to the makerspace first** (no cross-tenant existence disclosure). Frontend invalidates the
  printing **report** query on success so report grams aren't stale.
- **Superadmin soft-hide leak closed** (`5cb5e47`). `ManagedPrintRequestQuerysetMixin` and
  `NeedsFixShelfListView` now apply `rbac.hide_from_superadmin` when **no** `?makerspace=` filter is
  given (they previously returned hidden-makerspace rows incl. requester PII). Explicit
  `?makerspace=<id>` still returns data (the soft escape hatch — the queued hard-hide will close it).
  Payment totals (`reports._payment_summary`) now `.filter(status__in=COMPLETED_STATUSES)` so a
  drifted non-terminal row can't inflate paid/outstanding cash.
- **Lend attribution + deterministic lending history** (`8f8d7e0`). Per-item lending history orders
  `-request__issued_at, -request__id` (stable on ties) with a stable row `id` for React keys, and
  exposes `issued_by`/`accepted_by` ({username, role}). `AdminRequestSerializer` exposes the same on
  the Requests queue. Frontend renders "Accepted by / Issued by" in the lending-history drawer, the
  Requests/handover queue, and the direct-loans list.

## Recent batch — direct-handout UX, lending history, manual print log, QR rebind (2026-06-16)

Four features (Codex plan-reviewed v1→v2, then per-phase Codex code review; committed phase-by-phase).
Two migrations (`hardware_requests/0013`, `printing/0009`):

- **Direct handout shows all in-stock products + container + blocking check-in verify** (commit
  `9cc6336`). `direct_loan_workflow._manual_product` no longer requires `is_public`/
  `public_self_checkout_enabled` (those gate ANONYMOUS public self-checkout, wrong for a staff
  `ISSUE_DIRECT_LOAN` action) — staff can now hand out any non-archived **quantity** product (individual
  still needs a scanned asset QR); `DirectLoans.tsx` `eligibleProducts` mirrors it. New optional
  **container** FK on `PublicToolLoan` (migration `0013`, attribution note only) with a partial-unique
  `uniq_active_loan_per_container` (a physical container is out on at most one active direct loan;
  workflow pre-checks for a clean 409) — picked from `/admin/makerspace/<id>/containers`, shown in the
  loans list. New **`POST /admin/makerspace/<id>/checkin/verify`** (`ISSUE_DIRECT_LOAN` + active +
  `require_module('self_checkout')`, throttle scope `staff_checkin_verify`) returns **only `username`**
  (not `external_id`); the frontend Verify button **blocks Issue until verified** and re-binds to the
  exact identifier (`verifiedIdentifier === identifier`) so editing mid-flight can't approve a stale id.
- **Per-item lending history (audit-capable staff only)** (commit `499d7d4`). New
  **`GET /admin/inventory/<pk>/lending-history`** (`apps/admin_api/views_lending_history.py`): scopes
  PRODUCT-FIRST via `scope_by_action(VIEW_AUDIT, InventoryProduct)` then **`hide_from_superadmin`**
  (borrower PII respects the superadmin soft-hide), and reads the unified lend source
  `HardwareRequestItem` (`issued_quantity>0`, `request__issued_at` set, ordered desc, top 3) → last
  borrower + last 3 lends. Frontend: a lazy `LendingHistory` block in the Inventory item detail drawer,
  mounted only when `canViewAudit` (superadmin / space manager / inventory manager — **not** guest admin).
- **Manual print log** (commit `59cc5f6`). New `printing.ManualPrintLog` (migration `0009`) +
  **`GET/POST /printing/manage/manual-logs`** (`CanManagePrinting`). The community logs an ad-hoc print
  (`services_manual_logs.log_manual_print`, atomic): validates printer/spool makerspace + spool↔printer
  compatibility + active, **rejects overdraw** (`grams_used > remaining`, mirroring the print-start
  invariant), decrements the spool, audits `print.manual_logged`. Reports: `_filament_used` (initial −
  remaining) auto-reflects the deduction; `_printer_outcomes` **merges manual grams + a `manual_logs`
  count per printer, including manual-only printers**. Frontend: a "Manual print log" form + recent list
  on the 3D Printing panel (invalidates spools **and** printers queries on success).
- **Rename + rebind a saved QR across makerspaces** (commit pending). New
  **`POST /admin/qr/<pk>/rebind-target`** (`apps/boxes/rebind.py`, no migration): re-points a saved
  physical QR to another product (or same-makerspace asset) and optionally renames it. Locks the QR +
  target; requires ACTIVE; **blocks an outstanding loan (409)** and a destination that already has an
  active QR (409). Cross-makerspace moves (`target.makerspace != qr.makerspace`) are **superadmin-only**
  (mirroring cross-makerspace transfers) and **product-only** (assets stay tenant-bound); same-makerspace
  needs `MANAGE_QR`+`EDIT_INVENTORY`. Moves `qr.makerspace`/`target_*` (payload unchanged; old
  `QrScanEvent` rows keep their immutable makerspace), writes a `REASSIGNMENT` scan event in the new
  makerspace, audits `qr.rebound` + `inventory.renamed`. `new_name` capped at 100 (clean 400, not a DB
  error). Frontend: a Scanner-panel "Rename & rebind" form (superadmin gets a destination-makerspace +
  product picker) shown **only for product QRs**.

## Recent batch — staff-private cash payment on 3D print requests (2026-06-16)

Lets the print manager charge cash for a print, collected on trust at handover, **never exposed to
the requester** (Codex plan-reviewed; 466 backend tests green). One migration (`printing/0008`):

- **Model.** `PrintRequest` gains `price` (`Decimal(8,2)`, default 0, ≥0 — `0` = free), `payment_status`
  (`none`/`pending`/`paid`, default `none`), `paid_at`, `collected_at`, `collected_by` (FK user,
  SET_NULL), and a new terminal status **`COLLECTED`**. The lifecycle is now
  `pending → accepted(price set) → printing → completed → collected`; `accepted` still doubles as the
  "waiting to be printed" queue and `failed`/`rejected` stay terminal + non-collectable.
- **Workflow (single source of truth, atomic/row-locked/audited).** `workflow.accept(pr, actor, *,
  price=0)` validates + stores the price (Django-admin `accept_selected` passes 0 = free). `complete`
  sets `payment_status = pending if price>0 else none` (status stays `completed` = "ready to collect").
  New `mark_collected(pr, actor)`: `completed → collected`, always sets `collected_at`+`collected_by`;
  if `price>0` sets `payment_status=paid`+`paid_at`; audited `print.collected`, **no email**. `reprint`
  clones carry `price` with `payment_status` reset to `none`.
- **Privacy = serializer split (the load-bearing rule).** `PrintRequestSerializer` is shared by the
  requester AND public-status surfaces, so it stays **price-free**. A new
  `ManagedPrintRequestSerializer(PrintRequestSerializer)` adds `price`/`payment_status`/`paid_at`/
  `collected_at`/`collected_by` and is used **only** by the `/printing/manage/...` staff endpoints +
  action responses. New `PrintAcceptSerializer` (`DecimalField` price). New endpoint
  `POST /printing/manage/requests/<id>/collect` (`MANAGE_PRINTING`). Tests assert price never leaks to
  the requester list/detail, the public token status, status-by-email, or the text/HTML emails.
- **Reports.** Production metrics (printer hours, outcomes, filament-by-period) now count
  `status__in=[COMPLETED, COLLECTED]` (a collected print was still produced). New `payments` block —
  `paid_amount`/`paid_count`/`outstanding_amount`/`outstanding_count` (amounts as **Decimal**, not
  float) — per-makerspace and in the superadmin aggregate, respecting the soft-hide. Also fixed a
  **pre-existing soft-hide bypass**: `MakerspacePrintingReportView` now 404s when a superadmin queries
  a `superadmin_access_enabled=False` makerspace's report by id (the aggregate path already excluded it).
- **Frontend.** Accept opens an `AcceptPrintDialog` (price input, 0 = free); the staff queue gains an
  always-visible **"Ready for collection"** section (completed requests) with a **Mark collected**
  action and a payment badge (Free / Payment due / Paid); history now lists Collected/Rejected/Failed.
  The public stepper gains a **Collected** step (no price shown). The 3D-printing report panel shows a
  **Payments** sub-section (Collected vs Outstanding) + a Collected stat/pie slice.
- Also fixed (Codex P2 from the prior batch): `ApiClientSerializer` now drops the privileged
  `client_type`/`scopes`/`rate_limit_tier` for non-superadmins, so a makerspace admin using the new
  self-serve API-client surface can't escalate to a `trusted` tier or add `admin:write` scopes.

## Recent batch — collaborative-makerspace self-governance (2026-06-16)

Lets a collaborating makerspace operate independently of the superadmin. Five features (Codex
plan-reviewed v1→v6; 443 tests green):

- **Per-makerspace superadmin-access toggle (SOFT hide).** New `Makerspace.superadmin_access_enabled`
  (default True; migration `makerspaces/0013`). When False the space's DATA is excluded from the
  **superadmin's aggregate/list surfaces only** — `operations.reports` aggregate (all base helpers
  incl. the new `_assets()`, and `_summary()` routed through them), `operations.ledger` aggregate,
  `printing.reports` aggregate, `AuditLogListView` (applied **before** the `?makerspace=` filter so a
  superadmin can't explicitly query a hidden space), `StaffListCreateView` superadmin branch, and the
  Django `/control/` changelists. Core rbac scope functions are **untouched** (so this is a soft hide,
  not a hard 403 — the superadmin keeps raw staff-API + DB access; that's out of band by design).
  Helpers: `rbac.superadmin_hidden_makerspace_ids()` + `rbac.hide_from_superadmin(actor, qs, field)`.
  Django admin: `SuperuserOnlyModelAdmin.resolve_hidden_lookup()` auto-detects a direct `makerspace`
  FK (else a central `NESTED_MAKERSPACE_LOOKUPS` map; non-scoped models live in `GLOBAL_ADMIN_MODELS`)
  and `get_queryset()` excludes hidden rows; a drift-guard test (`tests/test_admin_hidden_scope.py`)
  walks every registered admin's relations to depth 3 and forces an explicit scoped/global decision so
  a new admin can't silently leak. **Re-grant (False→True) is makerspace-admin-only** — enforced in
  `MakerspaceSerializer.update()` with `transaction.atomic()` + `select_for_update()` against the FRESH
  value (stale-PATCH-proof); a superadmin attempt 400s. Disabled rows are served to the superadmin via
  a slim `MakerspaceDisabledRowSerializer` (id/name/slug/public_code/location/flag only — no
  public_api_key/SMTP/CORS leak) in both list + detail GET. Frontend: create-form checkbox (superadmin),
  a **Settings** tab (`MakerspaceSettingsPanel`, MANAGE_MAKERSPACE) with the toggle (re-enable disabled
  for superadmin when off), and an "Superadmin access: Off" badge in `MakerspacePicker`.
- **API-client self-serve (reverses the prior superadmin-only governance).** `ApiClientListCreateView`
  + `ApiClientDetailView` moved from `IsActiveSuperAdmin` → `IsActiveStaff` + `require_action`/
  `scope_by_action(MANAGE_MAKERSPACE)` (404-before-403). The makerspace admin now creates/lists/deletes
  API clients with one-time secret reveal in `ApiClientsPanel` (gated on a new `canManageMakerspace`
  prop; non-managers keep the `ApiKeyRequest` flow, left intact).
- **Admin password reset (no-SMTP fallback).** `POST /admin/users/<pk>/reset-password` (IsActiveStaff)
  sets a validator-checked temp password + `must_change_password`, returns it once, **repeatable**.
  Guards: never a superadmin target; **existential** block — nobody (incl. superadmin) may reset a
  user who holds SPACE_MANAGER in **any** hidden makerspace (closes the reset-SM→login→re-grant bypass);
  non-superadmin may only reset users fully within their MANAGE_MAKERSPACE scope and never another
  Space Manager. Frontend: per-row reset action in the Users panel (`ResetPasswordModal`).
- **Self-service forgot/reset password via a COMMON instance SMTP.** `POST /auth/forgot-password` +
  `/auth/reset-password` (AllowAny; enumeration-safe generic 200; fail-safe try/except; IP +
  email-normalized throttles `password_reset_request`/`password_reset_email`/`password_reset_confirm`;
  `default_token_generator`; link from `PUBLIC_APP_BASE_URL`; reset-confirm re-checks active/access
  status; blacklists outstanding tokens). Sends via `integrations.email.platform_mail_connection()`
  which uses the instance-wide **Platform Email** settings — **never** per-makerspace SMTP (a tenant
  SMTP operator could otherwise intercept a global-account reset token = cross-tenant takeover).
  Frontend: LoginPanel "Forgot password?" + public `/reset-password` route (`ResetPasswordPage`).
- **Platform Email settings (superadmin).** Singleton `integrations.PlatformEmailSettings` (migration
  `integrations/0001`) with the SMTP password **encrypted** via `API_CLIENT_ENC_KEY` (same Fernet helper
  as makerspace secrets). `GET/PATCH /admin/platform/email-settings` (`IsActiveSuperAdmin`, write-only
  password + `smtp_password_set` bool, audited). React superadmin **Platform email** tab; registered in
  the `/control/` admin (Integrations group). `platform_mail_connection()` falls back to Django's
  `EMAIL_*` default backend only when no platform host is set.

## Recent batch — console parity: surfacing orphaned backend lifecycles (2026-06-16)

Audit-driven fix of a systemic class of flaw — backend lifecycle capabilities reachable in the
Django `/control/` admin but with **no React staff-console surface**, so features were dead/broken
for normal staff. Ten commit-per-phase fixes:

- **3D-print lifecycle parity.** `PrintQueueSection` now has a **Pending review** section
  (`status=pending`) with **Accept** / **Reject** (reason dialog) → `/printing/manage/requests/<id>/{accept,reject}`,
  plus a collapsible read-only **history** (completed/rejected/failed via `?status=` filters, lazy-loaded)
  surfacing the `reason`. The start-printer dropdown now filters to `is_active && status==='active'`
  (matching the backend `_assign_print_job` guard). `FailPrintDialog` was parametrized (title/label/placeholder)
  to double as the reject dialog. Before this, public print requests landed as PENDING with no React way to
  accept them (only the Django admin).
- **Telegram test-alert error handling.** `TelegramTestAlertView` now catches `TelegramDeliveryError` and
  returns `{delivered:false, detail}` (HTTP 200) instead of an uncaught 500; the unconfigured case returns a
  distinct "not configured" detail. `ApiClientsPanel` renders the detail. (A real delivery failure previously
  surfaced as a generic 500, indistinguishable from "not configured".)
- **Hardware: individual-tracked issue (was a blocker).** `AssignIssueModal` now collects `asset_qr_payloads`
  via the camera `QrScanner` (one AVAILABLE asset QR per accepted unit, aggregate across individual items) and
  sends them in the issue body. New `AdminRequestItemSerializer.tracking_mode` + `requires_asset_qr` drive which
  items need scans; individual items are shown read-only in the broken-reject list (backend blocks broken-reject
  on them). Before this, issuing **any** individual-tracked reviewed request failed with `INDIVIDUAL_HANDOUT_ERROR`.
- **Hardware: terminal history.** New `RequestHistoryView` at
  `GET /admin/makerspace/<id>/request-history` (ISSUE_REQUEST-gated) lists returned/rejected/closed_with_issue
  requests; `Queues` shows a lazy read-only History panel. `QueuesList` now renders requester contact email/phone,
  rejection reason, and per-item damaged/missing/needs_fix.
- **Evidence viewing.** `AdminRequestSerializer` exposes `issue_evidence_id` (direct FK) + `return_evidence_ids`
  (via the request's `ReturnEvent` rows; prefetched). `QueuesList` adds "View issue/return photo" buttons that
  fetch a short-lived signed URL from `GET /admin/evidence/<id>` and open it. Staff could upload but not view
  evidence before (only the Django admin could).
- **Stocktake count step (was a blocker).** `StocktakePanel` gained a per-stocktake **count-entry** UI POSTing
  to `/admin/stocktakes/<pk>/count-lines` plus a variance table from the detail. Without it a stocktake had zero
  lines and Apply was a no-op.
- **Intra-makerspace transfers for managers.** `StockTransferListCreateView.create` now validates the payload,
  computes `is_cross`, and requires only `EDIT_INVENTORY` for **intra**-makerspace moves (cross-makerspace stays
  superadmin-only, rejected before any service side effects). `StockTransferPanel` takes `canEditInventory` and
  shows the intra-space form to managers (makerspace selectors stay superadmin-only). Negative tenant-scope tests added.
- **Containers management.** New `ContainersPanel` (tab, EDIT_INVENTORY/MANAGE_QR roles) wires the existing
  container endpoints: edit/move (`/admin/containers/<pk>/move`), contents drawer (`/contents`), scan history
  (`/history`), and per-asset QR reprint (`POST /admin/assets/<pk>/qr` → `QrImage`).
- **Staff Scanner tab.** New `ScannerPanel` (tab) resolves a QR via camera or paste (`/admin/qr/resolve`) and
  wires the staff-reachable allowed_actions: **Revoke** (`/admin/qr/<pk>/revoke`, MANAGE_QR) and box **contents**;
  checkout/return/direct_handout are pointed to the Direct-handout flow (they need a borrower identity). The old
  orphan `/scanner` route had dead action badges and no nav link.
- **Tenant-frontend registry.** New `TenantFrontendsPanel` (tab, MANAGE_MAKERSPACE = Space Manager + superadmin)
  lists/creates/edits `TenantFrontend` rows via `/admin/makerspace/<id>/frontends` + `/admin/frontends/<pk>`.

Tests: `test_request_workflow.py` (request-history scope + requires_asset_qr + evidence ids),
`test_operations_api.py` (intra-transfer allowed for managers, cross-makerspace + cross-tenant denied with no
side effects), `test_telegram_integration.py` (test-alert delivered:false + detail). Full suite green (408).

## Recent batch — broken-at-handover, to-be-fixed shelf, email status (2026-06-16)

- **Reject-broken at handover + needs-fix shelf.** New `InventoryProduct.needs_fix_quantity` and
  `HardwareRequestItem.needs_fix_quantity` buckets (migrations `inventory/0008`, `hardware_requests/0012`);
  `needs_fix` is now part of the `total >= Σ buckets` constraint, so **every place that recomputes total
  (`availability.adjust_quantities`, `operations.services_stocktake`) includes it**. At issue,
  `availability.issue_items(request, rejects_by_item)` takes per-item `(broken, disposition)`: broken units
  leave `reserved` and go to `needs_fix` (disposition `needs_fix` → to-be-fixed shelf, stays in total) or are
  scrapped (disposition `remove` → total drops); the rest issue normally. `handover_workflow.issue_request`
  gained `rejects=[{item_id, broken, disposition}]` and **blocks broken-reject on INDIVIDUAL-tracked items**
  (quantity-mode only this pass — asset MAINTENANCE flip is future). The **to-be-fixed shelf** is
  `GET /admin/inventory/needs-fix` (list) + `POST /admin/inventory/<pk>/needs-fix` ({action: repair|scrap,
  quantity}) in `admin_api/views_needs_fix.py`, backed by `availability.repair_from_needs_fix` /
  `scrap_from_needs_fix` (EDIT_INVENTORY-gated, audited). Frontend: the **Assign + issue** modal has a per-item
  "reject as broken" count + disposition (To-be-fixed shelf / Remove from inventory); a new **To-be-fixed**
  staff tab (`NeedsFixShelf`, EDIT_INVENTORY roles only) lists shelf items with repair/scrap.
  Tests: `tests/test_handover_broken_reject.py`.
- **Public print status is email-based** (not token, not email-notification-dependent — many makerspaces lack
  SMTP). `POST /printing/public/<slug>/status-by-email` ({email}) returns `{results:[...]}` of the requester's
  recent requests (AllowAny, `request_status` throttle; enumeration-security intentionally waived per product
  call). The public page's status card is now an email form; the `?token=` deep-link still works as a fallback.
  The manual public-token box was removed.
- **Dark-mode form fields fixed.** `index.css` sets `color-scheme: light` / `dark` on `:root` / `:root.dark`
  so native controls (select popups, date/number spinners) follow the theme, plus a `:-webkit-autofill`
  override so autofilled inputs (e.g. the status-check email) stop painting a light background in dark mode.
- **Public status card.** Fixed the step labels overflowing in the narrow sidebar (2×2 centered grid,
  wrapping). The status serializer now exposes `estimated_minutes`, and while a job is `printing` the card
  shows a live "~Xh Ym left" countdown computed client-side from `started_at + estimated_minutes`
  (`StatusStepper`, ticks every 30s; "Finishing up" past the estimate).
- **Public scan consolidation.** Removed the catalog header "Scan a tool" button; the request panel's
  "QR checkout" tab is renamed **"Scan a tool"** and gained the camera `QrScanner` (was paste-only). The
  dedicated `/m/<slug>/checkout` page still exists by URL.

## Recent batch — printing/login/upload polish + unified Requests (2026-06-15)

QA-driven fixes across printing, login, uploads, and the staff console:

- **Printer hard-delete.** `ManagedPrinterDetailView.destroy` no longer blocks on historical
  references — `PrintRequest.printer`/`FilamentSpool.printer` are `SET_NULL`, so history survives with
  the printer cleared. It returns **409 only when an *in-progress* job references the printer** (a
  `PRINTING` request via `printer` **or** its `filament_spool__printer`), so a running print keeps
  attribution. The frontend delete invalidates printers+spools+requests queries.
- **Filament spool visibility.** The public `/printing/public/<slug>/spools` endpoint already filters
  `is_active=True`; the staff spool rows now show an **Active·public / Inactive·hidden** badge plus an
  **Activate** action (the fix for "my spool isn't showing publicly" — it was inactive). Staff spool
  colour is a **visible dropdown** (`SpoolColorInput`, `SPOOL_COLORS`; preserves custom values).
- **Unified Requests tab.** The staff "Queues" tab is renamed **Requests** (`StaffApp` tab key
  `requests`) and split into a `RequestsPanel` with **Hardware** + **3D Printing** headings. Role
  gating: `canSeeHardware` (space/inventory/guest + superadmin) and `canSeePrinting` (space/print +
  superadmin); Inventory Manager is hardware-only (the printing *management* tab is now hidden for it
  too, since it lacks `MANAGE_PRINTING`). The print queue moved out of `PrintingPanel` into the
  reusable `PrintQueueSection` (printer/spool management stays on the 3D Printing tab).
- **Public print form.** Removed the redundant free-text **Material**/**Color** fields — the filament
  **spool dropdown is the single source** (grouped by material via `<optgroup>`, options show colour +
  grams). Material/colour are derived from the chosen spool on submit. The **status tracker is now
  email-only**: the manual public-token box was removed (no enumeration); per-step status emails carry
  the `?token=` deep-link that auto-opens live status on the page.
- **Dev login persistence.** `docker-compose.yml` backend sets `AUTH_COOKIE_SECURE=False` +
  `AUTH_COOKIE_SAMESITE=Lax` so the 7-day refresh cookie survives over `http://localhost` (prod keeps
  the secure `None`/`True` defaults via its own env).
- **Public upload 403 fixed.** The dev backend was previously **not wired to MinIO** (empty S3 creds →
  every presigned POST 403'd at MinIO). `docker-compose.yml` now gives the backend
  `AWS_ACCESS_KEY_ID/SECRET=minioadmin`, internal `AWS_S3_ENDPOINT_URL=http://minio:9000`, and
  browser-facing `AWS_S3_PUBLIC_ENDPOINT_URL=http://localhost:9000`; MinIO CORS adds `http://localhost`.
  **MinIO is the self-hosted, free, S3-compatible object store running in the local Docker stack — no
  external/AWS service is used; the `AWS_*` names are just the S3 protocol.**

## Recent batch — public UX, login, API-key requests, admin parity (2026-06-15)

A multi-feature batch (8 phases) refined public flows, login, API-key governance, and Django-admin
parity:

- **Public 3D print request UX.** The public form no longer requires a bucket — `submit_public_print_request`
  resolves a per-makerspace default `PrintBucket` named **"Public Requests"** (`get_or_create`, savepoint-guarded
  against the `unique_together(makerspace, name)` race). Requesters can pick from the makerspace's **active
  filament spools** via the AllowAny `GET /api/v1/printing/public/<slug>/spools` endpoint
  (`PublicFilamentSpoolSerializer` exposes only id/material/color/remaining_weight_grams). The chosen spool is a
  **preference**, stored on a NEW `PrintRequest.requested_filament_spool` FK (SET_NULL) that is **distinct from the
  operational `filament_spool`** (which stays NULL until staff assign at start). A `PrintRequest.requester_name`
  field captures the requester's name. `source_link` is (and was) optional. Print status emails now include a
  **status link** (`PUBLIC_APP_BASE_URL` env + `/m/<slug>/print?token=<public_token>`) and the tracking token; the
  public print page reads `?token=` to auto-show status. Migration `printing/0005`.
- **Public self-checkout scanner (frontend).** `frontend/src/features/inventory/PublicSelfCheckoutPage.tsx`
  (route `/m/:slug/checkout`, linked from the catalog when the `self_checkout` module is on) drives the
  pre-existing AllowAny `PublicToolCheckoutView`/`PublicToolReturnView` (`/api/v1/public/<slug>/tools/{checkout,return}`):
  enter Check-In ID → scan the **physical** tool QR (camera) → Use/Return. No QR payload is ever rendered on a public
  page (preserves the physical-possession security model); the backend only resolves `public_self_checkout_enabled`
  items, so non-enabled items/boxes are never exposed.
- **Direct handout date.** `issue_direct_loan` no longer accepts a client `due_at`; it sets
  `due_at = now + makerspace.default_loan_days` (fallback 7). The datetime picker was removed from `DirectLoans.tsx`.
- **Printer delete.** `ManagedPrinterDetailView` is now `RetrieveUpdateDestroyAPIView`; DELETE returns **409** when the
  printer is referenced by any `PrintRequest` OR `FilamentSpool` (mirrors the spool-delete guard; preserves history),
  else deletes + audits. Frontend delete button added.
- **Login.** `LoginPanel` is a real `<form>` with `autocomplete="username"/"current-password"` (password-manager save).
  `StaffApp` restores the session on mount via a silent `POST /auth/refresh` (httpOnly 7-day cookie) → `/auth/me`
  hydrate. `api.ts` refresh/logout send `credentials:"include"` + `X-Refresh-CSRF` and logout calls `POST /auth/logout`.
  **`accounts.auth_cookies._origin_allowed` now also accepts dynamically-registered tenant origins** via the shared
  `makerspaces.cors.origin_is_registered` (so cross-origin refresh/logout don't 403 for registered frontends).
- **API-key governance (no keys in the React frontend).** ALL `ApiClient` REST endpoints (list/create/detail/update/
  delete) are **superadmin-only** (`IsActiveDjangoSuperuser`); the Telegram/SMTP `ApiIntegrationSettingsView` is
  unchanged. Non-superadmin staff can only file an **`ApiKeyRequest`** (`apiclients.models.ApiKeyRequest`, migration
  `0003`) via `GET/POST /api/v1/admin/api-key-requests` (create + list-own). Issuance + one-time secret reveal happen
  ONLY in the Django `/control/` admin: `ApiKeyRequestAdmin.approve_and_issue` calls `ApiClient.issue()` +
  `sync_makerspace_origins()`, reveals the secret to the superadmin via `message_user`, and **notifies the requester
  of approval/rejection with no secret** (`apiclients.notifications`, fail-safe). The React `ApiClientsPanel` was
  stripped of all key create/secret/list surfaces and now only files requests + (superadmin-gated) integration settings.
- **Inventory quantity math centralized.** The adjustment logic moved from `admin_api/views_inventory.py` into
  `inventory.availability.adjust_quantities(...)` (row-locked, negative-guard, records `InventoryAdjustment` + audit);
  both the admin API and the new Django-admin action call it.
- **Django `/control/` operational parity.** New superadmin admin actions route through services (never mutate
  status/quantity directly): inventory **Adjust quantities** (→ `availability.adjust_quantities`), hardware request
  **Set return due date** (→ `handover_workflow.set_return_due`), user **Restrict/Restore access** (audited like the
  API), and **safe delete** actions for printers/spools (API-style 409 reference guard). `UserAdmin` gained a
  makerspace-membership `list_filter`. Hardware **issue/return are deliberately NOT mirrored in the admin** — they
  require box-scan + photos + remark (hard rules), so they remain in the React evidence flow.

## Project Status

### Admin control plane (superadmin-only)

The **Unfold Django admin is the Super Admin's sole control plane**, mounted at **`/control/`**
(NOT `/admin/` — `/admin` belongs to the React staff console SPA route) and locked to
superadmins. It is also **not exposed on the public frontend port**: `frontend/nginx.conf` does
not proxy it, so multi-makerspace staff (who only have port 80) can never reach the Django console;
the superadmin reaches `/control/` only via direct backend access. Access is gated two ways:
`config.admin_access.AdminSuperuserOnlyMiddleware` (prefix derived from `reverse("admin:index")` →
`/control/`; the `/api/v1/admin/...` React staff APIs are NOT gated) denies
any authenticated non-superadmin, and `config.admin_access.SuperuserOnlyModelAdmin` is the first
base of every `ModelAdmin` so each model view requires an active `is_superuser`. Unfold sidebar
nav callbacks (`config/unfold.py`) are strict-active-superuser too. All other staff roles
(Space/Inventory/Guest/Print managers) operate **only in the React staff console** and have no
Django-admin access. Superadmin operations are exposed as Django admin actions that route through
the existing services (never mutating status directly): hardware-request **accept/reject/assign-box**
(`hardware_requests/admin.py`), stocktake **complete/approve/apply** + QR-batch **mark-printed** +
per-product **QR-asset generation** (`operations/admin.py`, `inventory/admin.py`), and print-request
**accept/reject/complete/fail/start** (`printing/admin.py`). `StockTransfer` admin is read-only
(transfers are created+applied via `operations.services.apply_stock_transfer`). Issue/return remain
React-only (deferred). Stocktake lifecycle services now take a fresh `select_for_update` row lock
before status transitions. **U-SEC:** django-axes admin-login lockout (backends
`[AxesStandaloneBackend, ModelBackend]`, disabled in tests via `tests/conftest.py`), a scoped
`login` throttle on the JWT `LoginView`, a dedicated `public_request_submit` throttle scope plus a
write-only `website` honeypot on the public submit (silent fake-success, no row created),
production-gated security headers (HSTS/SSL-redirect/secure-cookies/`SECURE_PROXY_SSL_HEADER`) +
always-on CSP via django-csp 4 (`CONTENT_SECURITY_POLICY`), and a `pip-audit` CI job
(`.github/workflows/security-audit.yml`). The global CSP `script-src` omits `'unsafe-eval'`;
because django-unfold ships the standard (eval-requiring) Alpine.js build, a tiny
`config.admin_access.AdminCspEvalMiddleware` (ordered immediately after `csp.middleware.CSPMiddleware`)
appends `'unsafe-eval'` to `script-src` **only for `/control/` responses** via django-csp's
per-response `_csp_update` attribute — the JSON API and the public Swagger/ReDoc docs stay on the
strict policy. Without it Alpine never initializes and the admin is unusable (command palette stuck
open, dead sidebar/`Esc`). Design spec:
`docs/superpowers/specs/2026-06-13-superadmin-admin-control-plane-design.md`.

**Admin reachability + self-host tooling.** The Django control plane (`/control/`) is deliberately
**NOT** reachable on the public frontend port: `frontend/nginx.conf` proxies `/api/`, `/static/`,
and the docs routes (`/docs/`,`/redoc/`,`/schema/`) to the backend but **does not proxy the Django
admin** — so makerspace staff on port 80 can never reach the Django console. The superadmin reaches
`/control/` only via direct backend access (dev: `http://localhost:8001/control/`; production: the
backend port is unpublished, so publish it to localhost or use a tunnel / `docker compose exec`).
The React staff console at `/admin` (port 80) is where Space/Inventory/Guest/Print managers and the
Super Admin do day-to-day work. Non-technical install path: `setup.sh` / `setup.ps1` (first-run wizard:
Docker check → generate secrets incl. a Fernet `API_CLIENT_ENC_KEY` → write root `.env` → build via
`docker-compose.prod.yml` + `docker-compose.build.yml` → wait for readiness → `setup_instance` →
print URL/creds), `docker-compose.build.yml` (build-from-source overlay; GHCR images are not yet
public), and `docs/setup-for-makerspaces.md`. TLS settings are env-gated (`ENABLE_HTTPS`, default
off) so the default HTTP-behind-nginx stack works; `CSRF_TRUSTED_ORIGINS` is env-driven for HTTPS.

**Per-makerspace integrations are backend-only and never leak.** `Makerspace` holds per-tenant
`telegram_bot_token` and `smtp_*` fields; the secrets (`telegram_bot_token`, `smtp_password`) are
encrypted at rest with `API_CLIENT_ENC_KEY` via `apps/makerspaces/secrets.py` and decrypted only in
delivery code (`integrations/email.py`, `integrations/telegram.py`). The admin/staff integration
serializer (`admin_api/api_client_serializers.py`) exposes them **write-only** + a `*_set` boolean —
never returning the value. Bootstrap returns only frontend-safe config (module flags, not secrets).
Two or three makerspaces sharing one SMTP/Telegram = enter the same credentials per makerspace
(stored/encrypted independently; rotation updates each). No shared-integration entity exists.

**Staff console + reporting + admin coverage.** The React staff console has a **Reports** dashboard
(summary + most-lent / top-borrowers / damaged-lost / recently-added with dependency-free bar charts
and CSV/XLSX export, a **3D printing** report section — printer hours, filament used per spool, and
estimated-filament buckets by month/day/hour — and a superadmin "All makerspaces" aggregate toggle);
a **Ledger** panel listing everything currently OUT of inventory and who holds it (reviewed-request
loans + public self-checkout + admin direct handouts, overdue-flagged, with a superadmin aggregate);
full **Users** CRUD (add staff by role+makerspace, restrict/restore, superadmin create-makerspace);
**stock transfers** — intra-makerspace moves relocate stock between containers; **makerspace→makerspace
transfers truly move available quantity** (superadmin only): `operations.services._apply_cross_makerspace_line`
deducts the source product's available/total and credits a find-or-create destination product (matched
by name, created private until the destination opts in), recording a dual `InventoryAdjustment`.
Individual/asset-tracked products can't cross makerspaces (their asset rows + QR scoping are tenant-bound); a paginated **audit log**; a one-time API-client secret
with copy/dismiss; and a request **status stepper** (Requested→Approved→Collected→Returned) on the
public request view + staff queues. Backend adds `apps.operations.ledger` + `apps.operations.reports`
(per-makerspace and superadmin-aggregate analytics/exports) and `apps.printing.reports`
(`reports_views.py`/`reports_serializers.py`). First-run `setup_instance` seeds `superadmin` /
`super123` and sets `User.must_change_password`, which the JWT login + `/api/v1/auth/me` surface and
`POST /api/v1/auth/change-password` clears; the staff console blocks behind a forced-change gate
until rotated. **Django admin coverage** is complete: every domain model is registered under the
superadmin-only control plane, with `PublicToolLoan`, `ReturnEvent`, `RequesterAccountability`,
`HardwareRequestItemAsset`, and `BoxScan` registered **read-only** (immutable/workflow-owned) and
`MakerspaceMembership` editable; every makerspace-scoped `ModelAdmin` carries a `makerspace`
`list_filter` so the superadmin can view/manage per makerspace. The admin remains superadmin-only by
design (U-SEC) — per-makerspace staff still operate solely in the React console. The Unfold sidebar
(`config/unfold.py`) is curated into grouped sections (Inventory · Requests & loans · Operations · 3D
printing · Accounts & access · Integrations · Audit & evidence) covering every registered model; a
test (`tests/test_admin_registration.py`) asserts every sidebar `reverse_lazy` link resolves so a
model rename can't silently break the nav. **Superadmin monitoring surfaces** (read-only, no new
RBAC/migrations) let the control plane mirror what the React console shows: `QrPrintBatchAdmin` has a
**Download QR ZIP** action (reuses `operations.qr_zip.build_batch_zip`, one batch at a time);
`QrCodeAdmin` and `InventoryAssetAdmin` render an inline **QR preview** (`boxes.qr_render.render_qr_label_svg`;
the asset preview only shows an *active, same-makerspace* `QrCode`); `EvidencePhotoAdmin` renders
issue/return **photos** inline + a changelist thumbnail via short-lived signed URLs
(`evidence.storage.presigned_get_url`); and `PrintRequestAdmin` lists attached `PrintRequestFile`
**downloads** via `printing.storage.print_get_url` (images inline, STL/PDF as links). All HTML is built
with `format_html`/`format_html_join` and guards storage failures so a changelist never 500s. Because
those thumbnails load from object storage, `config.admin_access.AdminCspEvalMiddleware` also appends the
`AWS_S3_PUBLIC_ENDPOINT_URL` origin to `img-src` **only for `/control/` responses** (the global
`CONTENT_SECURITY_POLICY` is untouched; QR data-URI SVGs are already covered by `img-src 'data:'`).
Covered by `tests/test_admin_monitoring.py`.

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

> The detailed PRDs (`docs/prd-*.md`) are **internal planning docs kept local only** — they are
> intentionally not committed to the public repo (gitignored). References to "the PRD §N" below
> point to those local documents.

Implemented (multi-frontend platform):

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
- API-client browser/server type, scope metadata, and scope enforcement for
  protected API traffic.
- Per-client rate-limit tiers (`apps/apiclients/throttling.py`
  `ClientTierRateThrottle`): only HMAC-signed **server** clients get their
  configured tier (`client_public`/`client_standard`/`client_trusted`), keyed by
  `client_id`. Browser clients (publishable `client_id` + `Origin`, both
  forgeable) and anonymous traffic fall back to the view's scoped IP rate and can
  never claim an elevated tier. The middleware attaches `request.api_client` only
  after verifying the HMAC signature.
- Generated TypeScript API client from OpenAPI
  (`frontend/scripts/generate-api-client.mjs`, `frontend/src/generated/api.ts`).
- Dedicated frontend routes for public catalog, public item detail, kiosk,
  scanner, staff admin, guest admin, and superadmin surfaces.
- Scanner QR resolve endpoint with immutable scan events and allowed-action
  responses for box/product/asset/request QR payloads.

Implemented (open-source ops and reporting):

- `GET /api/v1/health/` and `GET /api/v1/health/readiness/`.
- `setup_instance` management command for first superadmin and first makerspace.
- Production-image Compose file (`docker-compose.prod.yml`), root `.env.example`,
  Docker health checks, and `docs/self-hosting.md`.
- Staff refresh lifetime is 7 days in SimpleJWT settings.
- The submitted-request Telegram alert includes requester username, contact
  email, contact phone, `requested_for`, and each requested item with its
  quantity (built in `notifications._build_submitted_request_message`, sent as
  plain text with no `parse_mode`, length-capped under Telegram's 4096 limit).
- Guest admins can process returns for scoped makerspaces through the same
  audited return workflow as staff.
- `apps.operations` with stock transfers, stocktake sessions/lines,
  inventory adjustments, analytics summaries, CSV/XLSX exports, QR print
  batches with **bulk ZIP download** (`apps.operations.qr_zip.build_batch_zip`:
  each QR is a captioned SVG — segno PNG-data-URI embedded in an SVG with the
  name below, dependency-free; the old A4 print-HTML endpoint was removed),
  container APIs, and bulk asset QR generation.
- First-pass admin frontend panels for transfers, stocktake, reports, QR batches,
  compact operations navigation, saved local inventory views, inline details,
  and bulk public QR enable/disable actions.
- Light theme is now default with a persistent dark theme toggle.
- Docker image publishing workflow for GHCR
  (`.github/workflows/docker-images.yml`).
- Public item detail pages backed by a safe public detail API.
- Serialized handout enforcement in BOTH handout paths: individual-mode
  (`tracking_mode == INDIVIDUAL`) products require scanned asset QR payloads.
  Direct handout rejects unscanned individual products; the reviewed-request
  issue flow (`handover_workflow.issue_request(..., asset_qr_payloads=...)`)
  requires one scanned AVAILABLE asset per accepted unit, flips each to `ISSUED`,
  and records a `HardwareRequestItemAsset` link + `QrScanEvent`. Returns use a
  count-based asset flip (the quantity resolution drives how many still-`ISSUED`
  links flip to AVAILABLE/DAMAGED/LOST; partial returns leave the rest issued).
  Quantity-mode handout/return is unchanged. `availability` remains the sole
  owner of quantity buckets; asset locks are taken QR→asset→product to match the
  self-checkout/direct-loan order.
- Full OpenAPI/Swagger coverage for the `operations` app (containers, stock
  transfers, stocktake, analytics, reports, QR print batches, asset units) via
  `@extend_schema`, with `(status, media_type)` mappings for the CSV/XLSX/HTML
  responses; snapshot `frontend/openapi-schema.json` + generated TS client kept
  in sync.
- Reusable staff-console UI primitives (`frontend/src/components/ui/`:
  `DataTable`, `FilterBar`, `BulkActionToolbar`, `StatusBadge`, `EmptyState`,
  `DetailDrawer`); the Inventory panel uses them (sortable dense table, bulk QR
  actions, saved-view search, item detail drawer). Other staff panels can adopt
  the primitives incrementally.
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
- **Admin theme:** Django admin themed with django-unfold (dark + purple, forced dark); site name configurable via `ADMIN_SITE_NAME` (default "Makerspace Manager")
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

- Public inventory page: `http://localhost:5000/m/makerspace`
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
  records for box/product/asset/scanner lookup scans. `qr_render.py`
  (`render_qr_label_svg`) renders a **namespaced standalone SVG** (segno PNG-data-URI
  embedded) shared by the QR-print view and the batch ZIP, so the staff `<img>` data-URI
  isn't a broken bare `svg_inline`. Staff direct handout supports **multiple items** and a
  real in-browser **camera QR scanner** (`frontend/src/components/ui/QrScanner.tsx`:
  native `BarcodeDetector` with a dynamic-imported `zxing-wasm` fallback) that resolves via
  `/admin/qr/resolve` and appends the scanned product/asset to the loan.
- `backend/apps/admin_api/` - staff REST surface for makerspaces, inventory CRUD,
  per-makerspace category CRUD (`makerspace/<id>/categories` + `categories/<pk>`,
  gated by `EDIT_INVENTORY` so Space + Inventory Managers manage their own
  makerspace's categories from the React console; superadmin still uses the Django
  admin; products set their category via `InventoryProductAdminSerializer`. Category
  detail scopes by `VIEW_INVENTORY` then requires `EDIT_INVENTORY` for write so a
  viewer gets 403 not 404; DELETE detaches products via the model's `SET_NULL` and
  audits `detached_product_count`),
  bulk inventory import preview/apply, staff membership management
  (`users/space-managers`, `users/inventory-managers`, `users/guest-admins`,
  `users/print-managers`), tenant frontend registry management, user
  restrict/restore, scoped API-client issuance, and audit-log reads.
- `backend/apps/operations/` - open-source ops/reporting slice: health checks,
  stock transfers (intra + true cross-makerspace movement), stocktake, inventory
  adjustments, analytics, ledger, CSV/XLSX report exports, container/location
  APIs, QR print batches with bulk ZIP download (`qr_zip.py`), and serialized
  asset QR generation. `views.py` / `services.py` are thin re-export barrels over
  domain submodules (`views_*`, `services_*`) to keep each file ≤200 LOC.
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
  `backend/templates/email/`. **Public 3D-print requests** mirror the
  hardware-request public posture exactly: `public_views.py`/`public_serializers.py`/
  `public_workflow.py` expose `/api/v1/printing/public/<slug>/{buckets,checkin/verify,
  uploads,requests}` + `/api/v1/printing/public/requests/<uuid:public_token>/status`
  (AllowAny + `ClientTierRateThrottle`, Check-In verify, honeypot-before-serializer decoy,
  `print_request_submit` throttle scope, atomic submit, no-PII/no-enumeration status by
  `public_token` + `external_checkin_user_id`). Multiple STL + screenshot uploads use a
  printing-specific presign (`storage.py`: server-generated `print/` keys, MIME/size
  allowlists, `PRINT_UPLOAD_MAX_BYTES`) staged as `PrintRequestFile` rows
  (`print_request` nullable + `owner_checkin_user_id` + `attached_at`) that submit attaches
  one-time inside the same transaction (`select_for_update`, owner+unattached+object_exists
  checks). `PrintRequest` gained `public_token`, `project_brief`, `contact_email/phone`;
  status emails route to `contact_email` (shadow users have no account email) and now cover
  submitted/accepted/started/completed("ready to collect")/rejected. Staff see brief/contact
  and download attached files via short-lived **signed view URLs**
  (`manage/files/<pk>/url`, never raw object keys). Filament spools are now deletable
  (409 when referenced by a request — FK is `SET_NULL`). Frontend: public
  `frontend/src/features/printing/` (request page + status stepper) linked from the public
  catalog when the `printing` module is on.
- `backend/apps/procurement/` — per-makerspace **"To Buy" / shopping list**
  (`ToBuyItem`: name, quantity, link, status pending|bought, estimated_unit_cost,
  `kind` hardware|printing). The stream is decided **server-side from the actor's
  role** (`access.derive_kind`), never trusted from the client: print managers'
  items are auto-tagged `printing`, Space/Inventory managers' are `hardware`; a
  makerspace admin (`MANAGE_MAKERSPACE`) / superadmin may target either. Visibility
  (`access.viewable_kinds`) follows the same matrix — Space Manager + Superadmin see
  BOTH streams, Inventory Manager sees hardware, Print Manager sees printing. No new
  RBAC action: it reuses `MANAGE_MAKERSPACE`/`EDIT_INVENTORY`/`MANAGE_PRINTING`.
  `views.py` is list/create + detail (404-before-403 across tenant+stream) + CSV
  export, all `@extend_schema`-documented; mounted at `/api/v1/procurement/`.
  Registered in the superadmin Django admin (Procurement sidebar group). Frontend:
  `ProcurementPanel.tsx` ("To Buy" tab; print managers get it in their printing-only
  nav; admins get a hardware/printing selector + CSV export).
- `backend/apps/hardware_requests/` — Hardware Request Workflow (submit + accept/reject + issue + return): `HardwareRequest`/`HardwareRequestItem`, the `HardwareRequestItemAsset` through model (per-unit issue/return links for individual-mode handouts, in `asset_link_models.py`), immutable `ReturnEvent`, and immutable `RequesterAccountability` models; `workflow.py` (single source of truth: `submit_request`/`accept_request`/`reject_request`/`assign_box`/`issue_request`/`return_items`, atomic + row-locked + audited; reserve-at-acceptance); `permissions.py` (`CanReviewRequest`, `CanViewHandoverQueue`, `CanReturnRequest`); `serializers.py` (strict public-status allowlist plus return item resolutions); `views.py` (public submit/verify/status under HMAC-protected `public/`; admin queues + accept/reject/assign-box/issue/return with 404-before-403 scoping); `exceptions.py` (workflow→HTTP exception handler + `ErrorSerializer`); `notifications.py` (Telegram seam); `urls.py`, `admin.py`.
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
- **Keep files modular — target ~200 lines per file, hard ceiling ~300.** One clear responsibility per file. When a module file grows past the target, split it (e.g. route handlers, validation, and service logic in separate files). The deep modules in §12 are logical boundaries, not single files. **Established split pattern:** when an app's `views.py`/`serializers.py`/`admin.py`/`services.py` outgrows the ceiling, split classes/functions into domain submodules (`views_*`, `serializers_*`, `admin_*`, `services_*`) and keep the original file as a **thin re-export barrel** (explicit `from .submodule import (...)`, never `import *`) so `from app.views import X` and `views.X` keep resolving; for `admin.py` the barrel must still import the admin submodules so the `@admin.register` side effects fire. Every backend code file is within the ceiling **except `backend/config/settings.py`** — Django settings are conventionally a single file (accepted exception).
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
