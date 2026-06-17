# Fix-batch plan — Codebase Analysis error report (HIGH + MEDIUM + LOW + lend attribution)

## Confirmed design decision (do NOT change)
Keep the superadmin soft-hide **404s** on per-makerspace report / ledger / lending-history
endpoints (intentional PII protection). The batch only **closes the #4 list leaks** so the
codebase is internally consistent (PII surfaces hide everywhere).

## Execution model
5 **file-disjoint** phases → run as parallel Codex implementation agents. After all return,
Claude verifies each diff against this plan, fixes deviations directly, runs backend pytest +
frontend typecheck/build, then Stage-4 background Codex review, then user QA. Only **one**
schema change in the whole batch (Phase 3 migration `printing/0010`).

---

## Phase 1 — Direct handout & self-checkout
Files: `backend/apps/hardware_requests/self_checkout_helpers.py`,
`direct_loan_workflow.py`, `direct_loan_views.py`, `direct_loan_serializers.py`,
`frontend/src/features/staff/DirectLoans.tsx`

- **#1 (HIGH) Staff QR handout must not require `is_public`/`public_self_checkout_enabled`.**
  Semantics: `public_self_checkout_enabled` = anonymous-kiosk eligibility; `is_public` =
  public-catalog visibility. Neither should gate a trusted staff `ISSUE_DIRECT_LOAN`.
  Approach: thread a `require_public` flag through the shared helpers —
  `_checkout_target(qr, *, require_public=True)`, `_eligible_product(pk, makerspace, *,
  require_public=True)`, `_eligible_asset(pk, makerspace, *, require_public=True)`,
  `_checkout_box(qr, *, require_public=True)`. Public caller `checkout_tool` keeps the default
  `True` (unchanged). Staff `issue_direct_loan` calls with `require_public=False`. When False:
  require only same-makerspace + not archived + available≥qty (asset: status AVAILABLE; box:
  all available non-archived contents regardless of public flags). Public flag checks stay
  intact when True.
- **#2 (HIGH) Reject INDIVIDUAL-tracked products on the product-QR path.** In
  `_checkout_target` PRODUCT branch, if `product.tracking_mode == INDIVIDUAL` raise
  `RequestValidationError("Individual-tracked products require a scanned asset QR.")`. Applies
  to BOTH callers (mirrors the serialized-handout invariant; the ASSET branch is already
  correct and unaffected). **Also** reject INDIVIDUAL-tracked products in the `_checkout_box`
  product-contents fallback (`self_checkout_helpers.py:82`) — that branch abstract-issues
  product rows with no asset IDs, so an individual-tracked product in a box would otherwise
  bypass the same invariant. (Codex review point #5.)
- **#6 (MED) Race-safe container pre-check.** In `issue_direct_loan`, `select_for_update()` the
  container `Box` row before the active-loan `.exists()` check. Wrap the `PublicToolLoan.create`
  in a **nested `transaction.atomic()` savepoint**; catch `IntegrityError` **outside** that
  inner block and raise `InvalidTransition` (clean 409). Catching `IntegrityError` directly
  inside the outer `transaction.atomic()` leaves the Postgres transaction aborted/unusable — the
  savepoint isolates the failed INSERT so the outer txn stays valid. (Codex review point #2.)
- **#7 (MED) Reject inactive container.** If `container.is_active` is False →
  `RequestValidationError("Container is not active.")` (mirrors other flows).
- **L2 (LOW) Module-gate `container_id`.** In `direct_loan_views.py`, only honor `container_id`
  when the `containers` module is enabled for the makerspace (else ignore/400, matching how
  container listing is gated). Confirm exact module key during impl.
- **Attribution (feature):** `direct_loan_serializers.py` expose `issued_by`
  (`{username, role}` from `loan.request.issued_by`); `DirectLoans.tsx` render "Issued by".

## Phase 2 — QR rebind
Files: `backend/apps/boxes/rebind.py`, `backend/apps/boxes/api_views.py`,
`frontend/src/features/staff/panels/ScannerPanel.tsx`

- **#5 (HIGH) Guard source QR type on cross-makerspace rebind.** In
  `_require_rebind_permission` cross branch, require BOTH `qr.target_type == PRODUCT` AND
  `target_type == PRODUCT`; else `ValidationError("Only products can be rebound across
  makerspaces.")`.
- **#8 (MED, CRITICAL handling) Lock the destination-QR conflict check.** Add
  `select_for_update()` to the `_target_has_qr` lookup. Wrap the constrained `qr.save()` in a
  **nested `transaction.atomic()` savepoint** and catch `IntegrityError` **outside** that inner
  block, returning a 409 `Response`. The view wraps `rebind_qr_target` in an outer
  `transaction.atomic()` (`api_views.py:263`), so a bare `except IntegrityError` around the save
  would try to return a 409 from an already-aborted Postgres transaction (it would itself
  error). The savepoint keeps the outer txn usable. (Codex review point #1 — the most important
  revision.)
- **L4 (LOW) Add explicit gate.** `QrRebindTargetView.permission_classes = [IsActiveStaff]`
  (keeps the existing `_require_rebind_permission` checks).
- **#9 (MED, FE) Picker scoped to resolved QR.** Rebind destination product picker must query
  the **resolved QR's** makerspace (`qr.makerspace_id`), not the console-selected makerspace.
- **#10 (MED, FE) Permission-gate the action.** `canRebind` must also require the user holds
  `MANAGE_QR` + `EDIT_INVENTORY` (not just `type === "product"`), so guest/view-only users
  don't see "Rename & rebind".

## Phase 3 — Manual print log
Files: `backend/apps/printing/services_manual_logs.py`, `printing/models.py`,
new migration `printing/0010_*`, `printing/views_manual_logs.py`,
`printing/serializers_manual_logs.py`,
`frontend/src/features/staff/panels/ManualPrintLogSection.tsx`

- **#3 (HIGH) Reject inactive/non-ACTIVE printer.** Inside the txn re-fetch the printer with
  `select_for_update()` and reject `not printer.is_active or printer.status !=
  PrintPrinter.Status.ACTIVE` → `InvalidTransition` (mirrors `workflow.py` print-start).
- **#11 (MED) Positive-grams service guard + DB constraint.** Service: reject `grams_used <= 0`
  → `InvalidTransition`. Model: add `CheckConstraint(grams_used__gt=0)` on `ManualPrintLog`
  (migration `0010`). Serializer min_value stays.
- **L3 (LOW) Tenant-first fetch.** In `views_manual_logs.py`, fetch printer/spool scoped to the
  makerspace first so a cross-tenant id returns the same "not found" as a missing id (no
  existence disclosure).
- **#12 (MED, FE) Invalidate report cache.** On manual-log success, also invalidate the printing
  **report** query key (in addition to spools/printers/logs).

## Phase 4 — Soft-hide leak + payment totals
Files: `backend/apps/printing/views_requests.py`,
`backend/apps/admin_api/views_needs_fix.py`, `backend/apps/printing/reports.py`

- **#4a (HIGH) Managed-printing list.** In `ManagedPrintRequestQuerysetMixin.get_queryset`, when
  `makerspace_id is None` apply `rbac.hide_from_superadmin(user, qs, "bucket__makerspace_id")`.
  Explicit `?makerspace=` keeps the raw escape-hatch access.
- **#4b (HIGH) Needs-fix list.** In `NeedsFixShelfListView.get_queryset`, when no `?makerspace=`
  apply `rbac.hide_from_superadmin(user, qs, "makerspace_id")`.
- **#13 (MED) Payment totals by lifecycle.** In `reports.py _payment_summary`, add
  `.filter(status__in=COMPLETED_STATUSES)` (constant already defined) before the aggregate so a
  drifted non-terminal row can't inflate paid/outstanding cash.

## Phase 5 — Lending history fix + Requests-queue attribution
Files: `backend/apps/admin_api/views_lending_history.py`,
`backend/apps/admin_api/serializers_lending_history.py`,
`backend/apps/hardware_requests/serializers.py`,
`frontend/src/features/staff/panels/Inventory.tsx`,
`frontend/src/features/staff/panels/QueuesList.tsx`

- **L1 (LOW) Deterministic ordering + stable keys.** `order_by("-request__issued_at",
  "-request__id")`; emit a stable id per recent row; `Inventory.tsx` use it as the React key.
- **Attribution (feature, lending history):** add `issued_by`/`accepted_by` (`{username, role}`)
  to each recent entry + `last_borrower`; serializer exposes; `Inventory.tsx` renders.
- **Attribution (feature, Requests queue):** `AdminRequestSerializer` expose `accepted_by` +
  `issued_by` (`{username, role}`); `QueuesList.tsx` render "Accepted by / Issued by".

---

## Stage 3 tests (Codex-required, run after implementation)
`backend/tests/` additions — assert external behavior, not implementation:
- Public checkout STILL requires public flags (no regression from #1).
- Staff QR direct handout ALLOWS a non-public / non-self-checkout product (the #1 fix).
- Public AND staff product-QR checkout REJECT an INDIVIDUAL-tracked product (#2); ASSET QR still
  works for INDIVIDUAL.
- Box-contents fallback rejects an INDIVIDUAL-tracked product (#2 box extension).
- Inactive container rejected (#7); duplicate active container → clean 409 not 500 (#6, exercises
  the savepoint).
- QR cross-makerspace rebind blocked when source QR is an asset (#5); duplicate destination QR →
  clean 409 not 500 (#8, exercises the savepoint).
- Manual print log rejected for inactive/non-ACTIVE printer (#3) and for grams ≤ 0 (#11).
- Superadmin managed-print list + needs-fix list EXCLUDE hidden-makerspace rows when no
  `?makerspace=`, but INCLUDE them with an explicit `?makerspace=<hidden id>` (#4).
- Payment totals exclude non-COMPLETED/COLLECTED rows (#13).

## Risks / things to confirm in review
1. #1 box-QR staff path: with `require_public=False`, scanning a **box** QR hands out ALL
   available non-archived contents (matches trusted-staff manual semantics). Confirm acceptable.
2. #2 rejecting INDIVIDUAL on the **public** product-QR path too is a (correct) behavior change,
   not just the staff path.
3. Attribution reads existing `accepted_by`/`issued_by` FKs — **no migration** needed.
4. Only schema change in the batch is Phase 3 `printing/0010` (additive CheckConstraint).
5. All 5 phases touch disjoint files → safe to run as parallel Codex agents; Phase 3 is the only
   migration-bearing phase.
