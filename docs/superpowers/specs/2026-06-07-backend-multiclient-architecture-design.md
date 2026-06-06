# Backend Architecture — Multi-Client, API-First (Design)

**Date:** 2026-06-07
**Status:** Approved (brainstorming) — pending written-spec review
**Scope:** Cross-cutting backend architecture that governs Phases 2–10. Not a single
implementation phase; it is the contract every phase below it must honor.

---

## 1. Goal

One backend serving **many independent frontends** over different origins:

- Per-makerspace public sites (e.g. `kochi.tinkerspace.in`) — read-only browse + check-in.
- A staff admin app (e.g. `admin.tinkerspace.in`) — authenticated operations.
- Third-party makerspaces building their own clients later (server-to-server).

The backend is a **pure, versioned JSON API**. No endpoint assumes a specific frontend.

## 2. The three identity layers

These are independent and composable. A request can carry a client identity *and* a
user identity.

| Layer | Who | Mechanism | Guards |
|---|---|---|---|
| **Client (browser)** | Public SPAs (Kochi public, admin app) | Non-secret **publishable `client_id`** + `Origin` | CORS allowlist + rate limiting |
| **Client (server)** | Third-party / server-to-server | `client_id` + **HMAC secret** signature | `X-Signature` over body+timestamp, replay window |
| **User (staff)** | superadmin / admin / guest-admin | **JWT** (access in memory, refresh in cookie) | RBAC + makerspace scoping |

Key rule: **a browser never holds an HMAC secret.** Anything in a JS bundle is public,
so browser clients get a *publishable* (non-secret) id only. HMAC is reserved for
clients that run server-side and can keep a secret.

### 2.1 Client registry — `ApiClient`

```text
ApiClient
- id
- client_id            # public, unique, prefixed (e.g. "pk_..." / "sk_...")
- name
- client_type          # publishable | server
- hmac_secret_hash     # nullable; set only for server clients (never stored plaintext)
- makerspace           # nullable FK; null = global; set = scoped to one tenant
- allowed_origins      # for publishable clients → feeds CORS + Origin check
- rate_limit_tier
- is_active
- created_at
```

- **Publishable** clients: request is accepted if `client_id` is active and `Origin`
  is in `allowed_origins`. No signature.
- **Server** clients: request must carry `X-Client-Id` + `X-Timestamp` + `X-Signature`
  where signature = HMAC-SHA256(secret, `timestamp + method + path + body`), within a
  small replay window. Secret is shown once at creation, stored only as a hash.

## 3. API surface organization

- **Versioned:** everything under `/api/v1/`.
- **Public surface** `/api/v1/public/*` — anonymous; publishable-client gated; no user
  auth. (Current public inventory browse moves here.)
- **Staff surface** `/api/v1/admin/*` and `/api/v1/guest-admin/*` — JWT required + RBAC.
- **Auth** `/api/v1/auth/*` — login/refresh/logout/me.
- **Integrations** `/api/v1/integrations/*` — Telegram webhook etc. (later phases).

A public frontend physically cannot reach staff routes (separate path namespace +
permission classes), and CORS is credentialed per registered origin — never `*`.

## 4. Invariants reaffirmed (from CLAUDE.md / PRD)

- **RBAC + makerspace scoping** gate every staff query (Phase 2 builds the shared layer;
  all later phases reuse `scope_by_makerspace`). Forgetting it = cross-tenant leak.
- **All quantity math** flows through the Inventory Availability module — including
  inter-makerspace transfers. "Availability never < 0."
- **Audit log is append-only**; every state-changing endpoint emits an entry.
- **Evidence photos & QR scans are immutable.**

## 5. Revised roadmap (value-first order)

```
2.  Auth + RBAC + scoping  +  API-first foundation
      (versioned /api/v1, CORS allowlist, public/staff split,
       ApiClient registry + publishable-key gate for browsers)
3.  Request workflow + minimal admin frontend (pending → accept/reject)  ← visible loop
4.  Evidence/photos (object storage) + audit log
5.  QR/boxes + Issue flow (handover w/ box scan + photo)
6.  Return flow (return photo + remark + per-item condition)
7.  Inventory Availability module hardening
8.  ★ Inter-makerspace transfer (superadmin-only, audited)   ← needs 7 + audit (4)
9.  Ledger / reporting (per-makerspace "what's taken", request logs)
10. API hardening: HMAC server-client signing, rate limits, third-party onboarding
```

MVP core = phases 2–7. **The entire multi-client `ApiClient` registry — both the
publishable-key browser path and HMAC server-signing — is deferred to Phase 10**
(decided at plan time). A working single-client `FrontendHMACMiddleware` already guards
the public surface (`backend/apps/inventory/middleware.py`); it stays as-is until Phase 10
replaces it with the registry. Phase 2 therefore does **not** build `ApiClient`; it builds
staff JWT auth + RBAC + scoping + the `/api/v1/` versioning skeleton.

## 6. Open questions (resolved at the owning phase, not now)

- **Transfer semantics (Phase 8):** move into an existing destination product (matched by
  admin selection) vs auto-create a destination product; whether a `StockTransfer` record
  is needed for the ledger.
- **Check-in API shape (Phase 4):** request/response of the external verifier (PRD §18).
- **Rate-limit tiers / quotas (Phase 10).**
- **HMAC canonicalization details (Phase 10):** exact signing string, clock-skew window.
