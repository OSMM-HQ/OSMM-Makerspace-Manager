# Contributing to OSMM

Thanks for contributing! This guide covers how to get set up, the conventions we follow, and how
to get a change merged.

## Getting started

1. Fork and clone the repo.
2. Follow **[README.md → Development](README.md#development)** to run Postgres, the Django backend,
   and the React frontend locally.
3. Confirm the backend test suite is green before you start:

   ```bash
   cd backend && pytest
   ```

## Project layout

- `backend/` — Django 5 + DRF API. Apps live under `backend/apps/` (accounts, makerspaces,
  inventory, hardware_requests, printing, operations, integrations, audit, evidence, …).
- `frontend/` — React 18 + Vite + TypeScript (public catalog + staff console).
- `docs/` — self-hosting guide, handover notes, and design specs.

## Architecture rules (please don't regress these)

- **Workflow services are the single source of truth for state transitions.** Never mutate
  `HardwareRequest.status` (or other lifecycle status) directly — route through the workflow
  service so the audit log, Telegram alerts, and reservations stay consistent. The Django admin
  actions and the React console both call these same services.
- **The Inventory Availability module owns all quantity math** (reserve/issue/return/mark-lost).
  No other module computes available/reserved/issued counts. Availability never goes below zero.
- **Every makerspace-scoped query must be scoped through the Auth/RBAC module.** Forgetting this is
  a cross-tenant data leak, not just a bug.
- **The Django admin is superadmin-only.** All other staff work in the React console.
- **Immutability:** audit logs are append-only; evidence photos and QR scan records are immutable.
- **Public inventory must never expose** storage locations, box IDs, QR codes, scan history,
  evidence photos, requester history, or hidden counts.

## Conventions

- **Files stay modular** — aim for ~200 lines, hard ceiling ~300, one responsibility per file.
- **Document every API endpoint in OpenAPI** (drf-spectacular `@extend_schema`). An undocumented
  endpoint is incomplete.
- **Production-quality code:** validate inputs at the boundary, handle external-service failure
  explicitly (the Check-In API must fail safe), use structured logging, return typed errors, and
  emit an audit-log entry from every state-changing endpoint.
- **Tests:** add/extend pytest coverage under `backend/tests/` for behavior changes (test external
  behavior, not implementation). Keep the suite green.

## Branches & commits

- Branch from `main`: `git checkout -b feature/<short-slug>` (or `fix/<short-slug>`).
- Use clear, conventional commit subjects, e.g. `feat(inventory): …`, `fix(printing): …`,
  `docs: …`, `chore: …`. Keep the subject one line.
- Keep each PR focused on a single concern.

## Pull requests

1. Make sure `cd backend && pytest` passes and the frontend builds (`cd frontend && npm run build`).
2. Update docs (`README.md`, `docs/`, and `CLAUDE.md` if you change tooling/architecture) alongside
   the code.
3. Open a PR against `main` describing **what** changed and **why**, and call out any required env
   vars, migrations, or manual steps.
4. Be responsive to review feedback — verify suggestions technically rather than applying blindly.

## Reporting issues

Open a GitHub issue with: what you expected, what happened, steps to reproduce, and your
environment (local Docker vs. Supabase, OS, browser). For security-sensitive reports, please avoid
filing a public issue with exploit details — flag it privately to the maintainers first.
