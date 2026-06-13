# Implementation Plan — Complete both PRDs ("Everything" scope)

Goal: close all remaining gaps in `docs/prd-open-source-ops-and-reporting.md` and
`docs/prd-multifrontend-platform.md`, bring Swagger/OpenAPI to the repo's
"every endpoint documented" standard, and update `CLAUDE.md` to the true state.

Audit result: both PRDs are ~90–95% implemented. The remaining gaps are below,
ordered by risk (low → high). Each numbered phase is one atomic commit on the
current branch (`master`), committed only after its tests are green.

---

## Phase 1 — Swagger / OpenAPI for the `operations` app (LOW risk)

**Problem:** 64/72 views are documented, but `backend/apps/operations/views.py`
is ~17% documented (19–20 views with no `@extend_schema`; several return raw
dicts, CSV/XLSX files, or HTML that drf-spectacular cannot introspect). This
violates the repo rule "Document every API endpoint in Swagger / OpenAPI."

**Changes:**
- `backend/apps/operations/views.py` — add `@extend_schema` (tags + summary +
  request/response) to every view. Serializers already exist in
  `apps/operations/serializers.py` (`StockTransferSerializer`,
  `StocktakeSerializer`, `QrPrintBatchSerializer`, `EmptySerializer`,
  `GenericObjectSerializer`, etc.).
  - **File/HTML responses** (`ReportExportView` views.py:275/428,
    `QrPrintBatchPrintView`/`export` views.py:~342): `OpenApiResponse` alone does
    NOT set the media type. Use drf-spectacular's `(status, media_type)` response
    mapping keys, e.g.
    `responses={(200, "text/csv"): OpenApiTypes.STR,
    (200, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):
    OpenApiTypes.BINARY}` for the CSV/XLSX export, and
    `{(200, "text/html"): OpenApiTypes.STR}` for the print page. Declare
    `format=csv|xlsx` and `report_key` via `OpenApiParameter`.
  - **Dict responses** (`ContainerContentsView`, `ContainerHistoryView`,
    `AnalyticsView`, `AssetGenerateView`, `QrPrintBatchItemView`): define small
    typed response serializers in `serializers.py` (e.g.
    `ContainerContentsSerializer`, `AnalyticsSummarySerializer`,
    `AssetGenerateResultSerializer`) rather than bare dicts / the
    `GenericObjectSerializer` fallback, so the generated TS client gets real
    types. Analytics, which returns different shapes per `report_key`, can use a
    permissive typed wrapper documented as `OpenApiTypes.OBJECT` only where a
    precise schema is impractical.
- `backend/config/settings.py` — add new SPECTACULAR `TAGS`:
  Containers, Stock transfers, Stocktake, Analytics, Reports, QR print batches,
  Asset units, Health.
- Regenerate the snapshot + client:
  - `python manage.py spectacular --file ../frontend/openapi-schema.json`
  - `cd frontend && npm run generate:api` (regenerates `src/generated/api.ts`).
- Verify `python manage.py spectacular --validate` emits **no warnings** for
  operations endpoints.

**Tests:** a spectacular schema-generation test (assert no errors + key
operations paths present with tags). Reuse existing test patterns.

---

## Phase 2 — Telegram request alert content (LOW risk, real PRD gap)

**Problem:** `apps/hardware_requests/notifications.py:68` sends only
`"New hardware request #<pk> from <username>."` — missing requester email,
phone, `requested_for`, and the item list with quantities. Violates
ops PRD decision §119 and acceptance criterion §391. (CLAUDE.md currently
*claims* this is done — it is not; CLAUDE.md will be corrected in Phase 6.)

**Changes:**
- `notifications.py` — build the submitted-request Telegram message body to
  include: requester username, contact email, contact phone, `requested_for`,
  and each requested item line with quantity (from
  `request.items.select_related("product")`). Keep the existing accept/reject
  inline keyboard. Keep delivery fail-safe (existing `TelegramDeliveryError`
  catch). Escape/avoid Telegram markup injection (send as plain text or escape).
- No model changes (contact fields already exist on `HardwareRequest`).

**Tests:** assert the composed message string contains email, phone,
requested_for, and item quantities; assert delivery failure is swallowed.

---

## Phase 3 — Per-client rate-limit tier enforcement (MEDIUM risk)

**Problem:** `ApiClient.rate_limit_tier` (public|standard|trusted) and
`client_type` exist but are never enforced — throttles use fixed scopes in
`settings.DEFAULT_THROTTLE_RATES`. Violates multifrontend PRD user story §29 /
decision (rate limits tied to client type + makerspace).

**Anti-spoofing (Codex finding #4):** the tier must come from a *verified*
client, never from a raw `X-Client-Id` header. Today `FrontendHMACMiddleware`
verifies origin (browser) / signature+scope (server) but does **not** attach the
client to the request, and `_should_validate` short-circuits entirely when
`API_CLIENT_AUTH_REQUIRED` is false (settings.py:187). So:

**Changes:**
- `backend/apps/inventory/middleware.py` — when a client is successfully
  verified, set `request.api_client = client` (the trusted, verified row).
  Decouple *attachment* from the *reject* decision: on protected prefixes,
  attempt verification + attach `request.api_client` (or leave unset) regardless
  of `API_CLIENT_AUTH_REQUIRED`; only the 401 reject stays gated on that flag.
  This is the single verification path — the throttle never re-reads or trusts
  the raw header.
- New `backend/apps/apiclients/throttling.py` — `ClientTierRateThrottle`
  (subclass of `ScopedRateThrottle`). Because DRF derives the rate from `scope`
  (inventory/views.py:28, public_views.py:62 set `throttle_scope`), override
  `get_rate()`/`allow_request()` (NOT just `get_cache_key`): if
  `getattr(request, "api_client", None)` is a verified client, pick
  `client_public|client_standard|client_trusted` from its `rate_limit_tier` and
  key the bucket by `client_id`; otherwise fall back to the view's existing
  `throttle_scope` rate and IP-based key. Unverified callers can never reach the
  elevated tier. The throttle is one class that handles BOTH cases.
- **Replace (do NOT stack) the existing `ScopedRateThrottle` with
  `ClientTierRateThrottle`** on the public read/write views
  (inventory/views.py:28, public_views.py:62, self_checkout_views.py:22). DRF
  runs *every* class in `throttle_classes`, so keeping both would still cap a
  trusted client at the `public_read`/`request_submit` rate (Codex round-2
  finding). The views keep their `throttle_scope` attribute — that becomes the
  anonymous fallback rate inside the new throttle.
- `settings.py` — add `DEFAULT_THROTTLE_RATES` entries `client_public`,
  `client_standard`, `client_trusted` (env-overridable, e.g. 30/min, 120/min,
  600/min). The existing `public_read`/`request_submit`/etc. scopes stay (they
  are the anonymous fallback).

**Tests:** verified trusted-tier client gets the higher limit; standard tier
gets the lower; a spoofed `X-Client-Id` with no valid signature/origin gets only
the anonymous fallback rate; anonymous traffic still throttled by `public_read`.

---

## Phase 4 — Serialized per-unit handout enforcement in the request workflow (HIGH risk)

**Problem:** The **direct-loan** path enforces individual-mode (asset scans
required, `direct_loan_workflow.py:120`), but the **reviewed-request** issue
path (`handover_workflow.issue_request` → `availability.issue_items`) is pure
quantity math: an individual-tracked product can be issued through a normal
request with no asset scan and no specific unit tracked. Ops PRD §142/§44–45
and acceptance criteria require individual-mode products to require asset scans
"when configured", while quantity-mode keeps working unchanged.

**Design (through model — Codex findings #1, #2, #3):** a plain
`issued_asset_ids` JSON list cannot represent *partial* returns. Reviewed-request
items track cumulative `returned_quantity`/`damaged_quantity`/`missing_quantity`
(models.py:109) and a return can resolve only part of an issued item
(return_helpers.py:27); a flat id list can't say which specific unit came back
vs. is still out, risking double-flips on a later partial return. So use a
through model, not a JSONField.

- New model `HardwareRequestItemAsset` + migration:
  - `request_item` (FK → HardwareRequestItem, related_name="asset_links")
  - `asset` (FK → InventoryAsset)
  - `outcome` (choices: ISSUED | RETURNED | DAMAGED | LOST; default ISSUED)
  - `issued_at`, `returned_at` (nullable)
  - `return_event` (FK → ReturnEvent, nullable) for traceability
  - `UniqueConstraint(request_item, asset)` and an index on
    `(request_item, outcome)`. This gives per-unit return outcomes, queryability,
    and DB-level guards a JSON list can't.

- `issue_request(actor, request, evidence_id, remark, asset_qr_payloads=None)`:
  - For each accepted item whose `product.tracking_mode == INDIVIDUAL`, require
    scanned asset QR payloads resolving to `InventoryAsset` rows of that product,
    status AVAILABLE, count == `accepted_quantity`. Reuse the `seen_qr_ids`
    double-scan guard from direct_loan_workflow.py:32.
  - Create one `HardwareRequestItemAsset(outcome=ISSUED)` per scanned asset,
    flip each `InventoryAsset.status → ISSUED`, emit QrScanEvent (context ISSUE)
    + audit, alongside the existing `availability.issue_items` quantity move.
  - Quantity-mode items: unchanged (no payloads needed).
  - Individual item with missing/mismatched payloads →
    `RequestValidationError` ("Individual-tracked products require scanned asset
    QR codes for handout."), matching the direct-loan message.

- Return path (`return_workflow` / `return_helpers`): individual-mode items
  resolve **per asset** — the return resolution names which scanned assets are
  returned/damaged/lost (condition per unit); update each
  `HardwareRequestItemAsset.outcome` + `returned_at` + `return_event`, flip the
  `InventoryAsset.status` accordingly, and derive the per-item
  returned/damaged/missing **counts** from those outcomes to feed
  `availability.return_items` (so quantity buckets stay correct and the existing
  partial-return accounting is untouched). Quantity-mode returns stay
  quantity-based exactly as today. Reject re-resolving an asset already in a
  terminal outcome (idempotency / no double-flip).

- **Lock ordering (Codex finding #3) — same global order in issue and return to
  avoid deadlock:** (1) `locked_request(request)` →
  (2) `InventoryProduct` rows via `availability` (already ordered by pk) →
  (3) `InventoryAsset` rows `select_for_update().order_by("pk")` →
  (4) `QrCode` rows `select_for_update().order_by("pk")`. `availability.py`
  remains the **single owner of quantity buckets**; asset-status flips live in
  the workflow next to the availability calls (same separation as direct-loan).

- Update the issue endpoint (`handover_views.py`) + serializer to accept optional
  `asset_qr_payloads`; update the return endpoint/serializer to accept per-asset
  resolutions for individual-mode items.

**Tests (incl. concurrency):** quantity-mode issue/return unchanged;
individual-mode issue without scans rejected; correct scans → specific assets
ISSUED, then RETURNED/DAMAGED/LOST on (partial) return with correct bucket math;
wrong-product / already-issued / cross-makerspace asset rejected; **two
concurrent issues of the same asset** — exactly one succeeds; **concurrent
returns** don't double-flip; partial return leaves the still-out assets ISSUED.

---

## Phase 5 — InvenTree-like staff admin console (HIGH effort, frontend)

**Problem:** All operational endpoints exist, but `features/staff/` is basic
forms, not the dense, professional operations console the ops PRD asks for
(§47–51): dense sortable tables, filters, saved views, bulk-action toolbars,
item detail pages with stock/locations/QR/movement/stocktake/loan history.

`StaffPanels.tsx` is one large file of prompt-driven workflows and ad-hoc tables
(StaffPanels.tsx:188/265), so this phase is **NOT one atomic commit** — split
into four (Codex finding #7), each independently green:

- **5a — Primitives.** Add reusable UI in `frontend/src/components/ui/`:
  `DataTable` (sort/paginate), `FilterBar`, `BulkActionToolbar`,
  `DetailDrawer`/detail layout, `StatusBadge`, `EmptyState`. Keep existing
  light/dark theme tokens. No panel behavior change yet (commit on build green).
- **5b — Queue & handover refactor.** Move Queues / handover / return panels onto
  DataTable + FilterBar; keep the same workflow mutations + TanStack Query keys.
- **5c — Inventory + item detail page.** Inventory list onto DataTable with
  filters/saved views/bulk actions; add an item **detail page** wiring existing
  endpoints (stock, container contents/history, QR, analytics/active-loans) into
  one operational home.
- **5d — Ops/admin tables.** Transfers, Stocktake, Reports, Users, AuditLog,
  QrTools onto the shared primitives with bulk actions where multi-row ops exist.

All sub-phases: keep TanStack Query patterns (query keys, invalidation), respect
bootstrap module flags, do not rebuild routing or auth.

**Tests:** existing frontend test patterns — table filter/pagination, bulk
action affordances, permission-based visibility, no cross-makerspace leakage.

---

## Phase 6 — CLAUDE.md + docs reconciliation (LOW risk)

- Correct the inaccurate Telegram claim and document the real final state of all
  five phases (serialized handout enforcement, rate-limit tiers, Swagger
  coverage, UI console).
- Update the "Implemented from ..." PRD sections to match reality.
- Note the regenerate-schema command in the dev workflow if not present.

---

## Sequencing & gates

1. Commit order: 1 → 2 → 3 → 4 → 5a → 5b → 5c → 5d → 6. Each is its own atomic
   commit after green tests (commit-on-green). Phases 1–3 are independent and
   low-risk; Phase 4 is the correctness-critical backend change; Phase 5a–5d are
   the frontend split.
2. Codex executes each phase (Stage 2) driven by Claude prompts; Claude verifies
   each changed file group and fixes directly.
3. Stage 3 tests per phase (`cd backend && pytest`, frontend build/tests).
4. Stage 4 background Codex review before finalizing.
5. Stage 5 user QA gate, then commit with the three co-author trailers.

## Revision log (Codex Stage 1 round 1 → addressed)
- #1/#2/#3 Phase 4: replaced `issued_asset_ids` JSONField with the
  `HardwareRequestItemAsset` through model; specified per-asset partial-return
  outcomes and a single global lock order (request → product → asset → qr) with
  concurrency tests.
- #4/#5 Phase 3: middleware now attaches the *verified* `request.api_client`;
  throttle overrides `get_rate`/`allow_request` and falls back to the anonymous
  scope rate for unverified callers (no header spoofing).
- #6 Phase 1: switched to `(status, media_type)` response mappings with correct
  media types for CSV/XLSX/HTML, typed serializers for dict responses.
- #7 Phase 5: split into atomic sub-commits 5a–5d.

## Revision log (Codex Stage 1 round 2 → addressed)
- #5 Phase 3: `ClientTierRateThrottle` now **replaces** (not stacks with) the
  existing `ScopedRateThrottle` on the public views — DRF runs all throttle
  classes, so stacking would still cap a trusted client at the anonymous rate.
  Views keep `throttle_scope` as the in-throttle anonymous fallback.
