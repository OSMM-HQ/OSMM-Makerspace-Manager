# Plan — Superadmin access: SOFT hide → HARD block (follow-up, builds AFTER the fix batch)

## Goal
Convert `Makerspace.superadmin_access_enabled=False` from today's **soft** hide (data drops out of
superadmin aggregate/list surfaces; core RBAC `can`/`scope_by_action` untouched; superadmin keeps
raw staff-API + Django `/control/` + DB reach) into a **HARD block**: when OFF the superadmin
cannot read or act on that makerspace anywhere. Rationale: self-service forgot-password (common
Platform Email SMTP) is now the makerspace's recovery path, so the superadmin escape hatch is no
longer needed for recovery.

## What "hard" means (user-confirmed)
- **Block ALL staff-API + Django `/control/` access** to a hidden makerspace's data/actions for the
  superadmin.
- **Existence stays visible** (slim id/name/slug/public_code/location/flag row) — needed for
  governance + the break-glass below. No data, no operational actions.
- **Re-enable (False→True) stays space-manager-only** — superadmin still 400s on a direct flip.
- **Block turning OFF unless instance Platform Email SMTP is configured** (guarantees a
  forgot-password recovery path).
- **Break-glass:** the superadmin retains ONE narrow capability on a hidden makerspace — create or
  restore a **SPACE_MANAGER** account + reset its first-login password. That person logs in and
  re-enables. (Same capability as the create-time "set first password" exception.) No other action.
  ACCEPTED RESIDUAL RISK: this is a privilege-escalation path; it is deliberate + loudly audited.

> **Codex plan-review verdict: NEEDS_REVISION → revised below.** Key corrections folded in:
> a single centralized policy helper (not 3 independent edits), include `scope_by_makerspace`,
> membership-role-only behavior for a superadmin who is also a member, a safe multi-membership
> password-reset rule, model-specific `/control/` admin rules, a shared `platform_email_configured()`
> source of truth, and reconciling the old `hide_from_superadmin` call sites. RE-REVIEW after revision.

## Changes by area

### 1. Core RBAC — ONE centralized policy helper — `apps/accounts/rbac.py`
- Do NOT implement as three independent edits. Add a single chokepoint, e.g.
  `superadmin_hidden_block_applies(actor, makerspace_id, action=None)`, and route **all** RBAC entry
  points through it: `can()`, `scope_by_action()`, **`scope_by_makerspace()`**,
  `makerspaces_for_action()`, and `makerspaces_for_actions()`. (Review point #1 — `scope_by_makerspace`
  is used by request review/handover before object lookup at `review_views.py` / `handover_views.py`;
  omitting it leaves a 403-instead-of-404 escape.)
- The helper's distinction (review point #2):
  - Actor NOT (`is_superuser` or `role==SUPERADMIN`) → never apply the hide (normal members
    unaffected).
  - Superadmin with **no** explicit `MakerspaceMembership` for that makerspace → deny / filter out.
  - Superadmin **with** an explicit membership → do NOT grant global superadmin power there; evaluate
    that membership's role exactly as a normal member via `_MEMBERSHIP_ROLE_ACTIONS` (so a superadmin
    who is only a hidden-space PRINT_MANAGER does not get MANAGE_MAKERSPACE/MANAGE_STAFF/inventory).
- This cascades the hard block to every `/api/v1/admin/...` endpoint already routing through
  `require_action`/`scope_by_action`/`scope_by_makerspace` (404-before-403 preserved).

### 2. Reconcile existing soft-hide call sites (review point #7)
- `hide_from_superadmin()` must DELEGATE to the same `superadmin_hidden_block_applies` policy (so it
  honors the explicit-member rule) — or be REMOVED where `scope_by_action` is now authoritative
  (`AuditLogListView`, `operations` reports/ledger, `printing` reports aggregate).
- The fix-batch #4 explicit `?makerspace=<hidden id>` escape hatch (managed-print list +
  needs-fix list) must be **closed** under the hard block — explicit id now returns no data / 404,
  not raw rows. Update `printing/views_requests.py` + `admin_api/views_needs_fix.py` accordingly.
- The per-makerspace report/ledger/lending **404s** (confirmed design decision) stay.

### 3. Django `/control/` admin — MODEL-SPECIFIC rules — `config/admin_access.py` (+ `accounts/admin.py`)
- Generic hard block for all DOMAIN models: `SuperuserOnlyModelAdmin.get_object()` → 404 for a
  hidden makerspace's row (direct or via `resolve_hidden_lookup()`); deny change/delete; deny add
  scoped to a hidden makerspace. Don't rely on `has_add_permission()` alone (no target object).
- EXPLICIT exceptions (review point #5) — `Makerspace`, `User`, `MakerspaceMembership` are NOT
  generically hard-blocked (the plan requires the Makerspace row to stay visible + the break-glass to
  work): implement slim/read-only hidden behavior for the Makerspace row, and constrain
  `UserAdmin`'s membership inline/form/querysets so a hidden membership can't be edited except via the
  narrow SPACE_MANAGER break-glass path.
- Drift-guard test extends to object-level (not just changelist) for domain models + the three
  exception models.

### 4. Re-enable + block-OFF-unless-SMTP — `apps/admin_api/serializers_makerspaces.py`
- Keep the existing atomic + `select_for_update()` fresh-value re-enable guard (False→True =
  space-manager-only; superadmin 400s) at `serializers_makerspaces.py:75`.
- NEW: on True→False, require instance Platform Email configured. Add a shared
  `platform_email_configured()` helper in `apps/integrations/email.py` (checks `smtp_host.strip()`)
  so the guard and `platform_mail_connection()`/`send_password_reset_email()` cannot drift (review
  point #6). Else `ValidationError("Configure Platform Email before disabling superadmin access, so
  password recovery remains possible.")`. Applies to whoever toggles OFF.

### 5. Break-glass: SPACE_MANAGER create + password reset on a hidden makerspace
- `StaffListCreateView._can_create_staff_role()` (currently True for any superadmin/role at
  `views_users.py:116`): make the hidden-makerspace exception EXPLICIT and NARROW (review point #4):
  the only break-glass path is **superadmin creates a BRAND-NEW SPACE_MANAGER** user for the target
  hidden makerspace (`target_role == SPACE_MANAGER` only). It must **NOT** attach/restore an existing
  user via `get_or_create()` (`views_users.py:81`): if the requested username/email already exists,
  **reject** (the superadmin picks a different username) rather than silently grafting the existing
  account onto the hidden makerspace. (Recovery is unaffected — a fresh SPACE_MANAGER account
  re-enables just as well; existing locked-out accounts go through the password-reset rule below.)
- Admin password reset (`views_users.py:181` existential block): allow superadmin reset ONLY when
  the target has ≥1 **hidden** SPACE_MANAGER membership AND **no enabled-space** SPACE_MANAGER
  membership (avoids the multi-membership ambiguity that would reopen the reset→login→re-enable
  bypass for non-hidden spaces). Never a superadmin target; non-superadmins still can't reset a peer
  SM (review point #3). Consider making break-glass makerspace-targeted long-term.
- Audit both loudly (`superadmin.break_glass_space_manager_created` / `..._password_reset`).

## Migrations
- None — reuses `superadmin_access_enabled` + `PlatformEmailSettings` (review point #8). (Only if we
  later add an explicit break-glass marker would a migration be needed.)

## Risks
1. **RBAC blast radius:** the centralized policy helper is the highest-stakes edit in the repo. Must
   not block normal members, must honor the explicit-member rule, must not break tenant-bound flows.
2. **Break-glass escalation** accepted but tightly scoped (SPACE_MANAGER only, no data reads) +
   audited.
3. **Double-apply / contradiction** between the new policy and legacy `hide_from_superadmin` call
   sites — §2 resolves it; verify no surface both filters AND grants inconsistently.

## Tests (drift-guard heavy — review point #8)
- `can`, `scope_by_action`, `scope_by_makerspace`, `makerspaces_for_action`,
  `makerspaces_for_actions` all hard-block a hidden makerspace for a global superadmin.
- Superadmin who is an explicit member of a hidden space gets MEMBERSHIP-role access only (e.g.
  PRINT_MANAGER ≠ MANAGE_MAKERSPACE).
- Member space manager (non-superadmin) keeps full access to their (hidden) space.
- Superadmin CAN create + reset a SPACE_MANAGER for a hidden makerspace; nothing else.
- Hidden SPACE_MANAGER reset allowed only for unambiguous targets; a manager of BOTH a hidden and an
  enabled space is NOT resettable via this path.
- OFF refused unless Platform Email configured; re-enable still space-manager-only.
- `/control/` object detail/change/add/delete blocked for domain models; allowed (slim/narrow) for
  the three exception models.
- Fix-batch explicit `?makerspace=<hidden id>` now returns no data / 404.
