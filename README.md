<p align="center">
  <img src="docs/banner.svg" alt="OSMM — Open Systems Makerspace Manager" width="100%">
</p>

<h1 align="center">OSMM — Open Systems Makerspace Manager</h1>

<p align="center">
  Self-hostable, multi-tenant <strong>inventory &amp; 3D-printing manager</strong> for makerspaces —
  browse, borrow, track, and stay accountable, without spreadsheets.
</p>

<p align="center">
  <a href="LICENSE.md"><img alt="License: AGPL-3.0-or-later" src="https://img.shields.io/badge/license-AGPL-3.0-or-later%20Noncommercial%201.0.0-blue.svg"></a>
  <a href="https://github.com/OSMM-HQ/OSMM-Makerspace-Manager/actions/workflows/release.yml"><img alt="Release" src="https://github.com/OSMM-HQ/OSMM-Makerspace-Manager/actions/workflows/release.yml/badge.svg"></a>
  <img alt="Stack" src="https://img.shields.io/badge/stack-Django%206%20%C2%B7%20React%2019-0b7285.svg">
  <a href=".github/CONTRIBUTING.md"><img alt="PRs welcome" src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg"></a>
</p>

---

OSMM started inside the **TinkerSpace Kochi** community, from a simple need: make it easy for a
makerspace to know **what tools exist, who borrowed what, what's available, and how 3D-print jobs move
from request to done** — with enough traceability that accountability for shared gear is never a
guessing game. It's built by makers, for makers: run it at your space, fork it, remix it, or use it as
a starting point. If your community works differently, make it your own.

One deployment can host **many makerspaces** (tenants). Each owns its inventory, public URL, staff,
Telegram group, QR namespace, and audit scope — fully isolated from the others.

## Features

- **Public catalog** — browse by makerspace and category, request to borrow, and (when enabled)
  **QR self-checkout/return** with Check-In verification and photo evidence. No login required.
- **Full hardware lifecycle** — request → accept → issue (box QR scan + photo) → return (photo +
  remark) → accountability, all audited. Direct staff handouts too.
- **3D-printing manager** — public print requests, printer/spool management, filament tracking,
  slicer estimates, and an optional (staff-private) cash charge at collection.
- **QR everywhere** — boxes, tools, and individual assets; immutable scan history.
- **Role-based staff console** — 5 scoped roles; a superadmin-only Django control plane.
- **Reports & ledger** — what's out, who has it, overdue tracking, CSV/XLSX export.
- **Notifications** — per-makerspace Telegram alerts and async (Celery) email.
- **Traceable by design** — append-only audit log; immutable evidence photos and scan records.

## Quick start

OSMM runs entirely through Docker Compose — it brings up **PostgreSQL, Redis, MinIO storage, the
Celery worker/beat, and database migrations** and wires them to the app for you (the images don't bake
in any addresses; the compose file passes them in). Pick one path:

**Path 1 — Guided setup (easiest; builds from source).** One script generates all secrets, writes
`.env`, builds everything, and creates your first admin + makerspace:

```bash
git clone https://github.com/OSMM-HQ/OSMM-Makerspace-Manager.git
cd OSMM-Makerspace-Manager
bash setup.sh                                          # macOS / Linux
powershell -ExecutionPolicy Bypass -File setup.ps1     # Windows
```

It prints your URL and login when it finishes. (Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).)

**Path 2 — Prebuilt images (no local build).** Pull the two published images and start the stack —
after `cp .env.example .env` (fill in the few values it asks for):

```bash
export MAKERSPACE_IMAGE_TAG=latest        # or pin a version, e.g. 0.25.0
docker compose -f docker-compose.prod.yml up -d
```

This pulls **`ghcr.io/osmm-hq/osmm-backend`** + **`ghcr.io/osmm-hq/osmm-frontend`** and brings up the
full stack automatically.

## Documentation

| I want… | Go to |
|---|---|
| A **plain-language, non-technical** walkthrough | **[docs/setup-for-makerspaces.md](docs/setup-for-makerspaces.md)** |
| **Production** reference (env vars, TLS, upgrades, releases) | **[docs/self-hosting.md](docs/self-hosting.md)** |
| **Advanced** config (Telegram, HMAC, Supabase, cron) | **[.github/ADVANCED.md](.github/ADVANCED.md)** |
| **Develop / contribute** (run from source, tests, releases) | **[.github/DEVELOPMENT.md](.github/DEVELOPMENT.md)** |

## Roles & access

Access is scoped **per makerspace and per action**. Super Admin is global; every other role is a
per-makerspace membership.

| Role | Can do | Cannot do |
|---|---|---|
| **Super Admin** | Everything, globally: makerspaces, all hardware/printing/ops, staff, settings, API clients, audit; the Django control plane | — |
| **Space Manager** | Full hardware lifecycle, direct handouts, inventory, staff & settings — for their space | Other makerspaces; Django admin |
| **Inventory Manager** | Full hardware lifecycle + inventory + QR + evidence + audit — for their space | Printing, staff, settings; Django admin |
| **Print Manager** | 3D-printing lifecycle, printers & spools | Hardware, inventory, staff; Django admin |
| **Guest Admin** | Issue accepted requests + process returns (evidence/QR/remark) | Accept/reject, inventory, QR, direct handouts; Django admin |
| **Public** | Browse, request, self-checkout/return eligible QR tools (Check-In + photo evidence) | Anything authenticated |

> Roles are **defined by the system, not by users** — nobody can invent roles or grant themselves
> extra powers; they can only assign people to existing roles within their own makerspace.

Staff work in the **React console** at `/admin`; the superadmin-only **Django control plane** lives at
`/control/` (backend-only, never exposed on the public port). Two design rules are load-bearing — the
Request Workflow module is the single source of truth for state transitions, and the Inventory
Availability module owns all quantity math. Details in **[.github/CONTRIBUTING.md](.github/CONTRIBUTING.md)**.

## Hosting

**The goal is to self-host inside the makerspace, on your own server** — your data, your network, no
third party. The [Quick start](#quick-start) above is the recommended path. After it's up:

| Surface | URL |
|---|---|
| Public catalog | `http://localhost` |
| Staff console | `http://localhost/admin` |
| API | `http://localhost/api` (Swagger at `/docs/`) |
| Django control plane | `/control/` on the backend only — **not** exposed on the public port |

Create the first superadmin + makerspace (the wizard does this for you; for a manual instance):

```bash
docker compose -f docker-compose.prod.yml exec backend python manage.py setup_instance
```

With no arguments it seeds **`superadmin` / `super123`** and forces a password change on first login.
Pin `MAKERSPACE_IMAGE_TAG` to a version (e.g. `0.25.0`) in production — see
**[docs/self-hosting.md](docs/self-hosting.md)** for env vars, TLS, and upgrades.

**No server of your own?** OSMM is multi-tenant — partner with a nearby makerspace to run your space
as a tenant on their instance. **Prefer managed Postgres?** Point `DATABASE_URL` at any managed
Postgres (e.g. Supabase) and host the app anywhere; a fully-managed free-tier path is documented in
**[docs/supabase-deployment.md](docs/supabase-deployment.md)** (best for demo/pilot, not dependable
production).

## Tech stack

Django 6 + DRF · React 19 + Vite 8 + Tailwind CSS 4 + TypeScript (TanStack Query v5) · PostgreSQL 16 ·
Celery + Redis · MinIO (S3-compatible) · django-unfold admin · drf-spectacular / OpenAPI. Delivered as
two Docker images (`osmm-backend`, `osmm-frontend`); everything else is official upstream images.

## Contributing

OSMM is a collaborative project for the makerspace community, and **contributors are very welcome** —
code, docs, translations, or just running it at your space and reporting what's rough. See
**[.github/CONTRIBUTING.md](.github/CONTRIBUTING.md)**; pull requests require signing the
**[CLA](.github/CLA.md)** (an automated check walks you through it), and contributors get
[recognition and benefits](.github/CONTRIBUTOR-BENEFITS.md).

## License

OSMM is **source-available** (not OSI "open source") — free for noncommercial use, with commercial
rights reserved to OSMM-HQ.

- **Governing license:** [AGPL-3.0-or-later](LICENSE.md) (`AGPL-3.0-or-later-Noncommercial-1.0.0`).
- **Free, no approval needed** ([PERMISSIONS.md](PERMISSIONS.md)): a **noncommercial makerspace**
  (nonprofit, community group, club, or school — not operated for profit) may self-host OSMM to run its
  **own** space; nonprofits, schools, clubs, and individuals may use it internally; anyone may fork,
  study, and modify it for noncommercial use.
- **Needs a commercial license** ([COMMERCIAL.md](COMMERCIAL.md)): operating a **for-profit makerspace**
  on OSMM, reselling OSMM, hosting it as a paid service for others, or bundling it into a commercial product.

To request a commercial license, contact **OSMM-HQ** via [github.com/OSMM-HQ](https://github.com/OSMM-HQ).
