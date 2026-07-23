<div align="center">

  <img src="docs/banner.svg" alt="Space Works — Open Source Makerspace Manager" width="860">

  <h1>Space Works — Open Source Makerspace Manager</h1>

<p>
  Self-hostable, multi-tenant <strong>management platform for makerspaces</strong> — run your
  inventory, tool &amp; equipment lending, and 3D printing in one place. Browse, borrow, track, and
  stay accountable, without spreadsheets.
</p>

<p>
  <a href="LICENSE"><img alt="License: AGPL-3.0-or-later" src="https://img.shields.io/badge/license-AGPL--3.0--or--later-blue.svg"></a>
  <a href="https://github.com/SpaceWorks-HQ/SpaceWorks/actions/workflows/release.yml"><img alt="Release" src="https://github.com/SpaceWorks-HQ/SpaceWorks/actions/workflows/release.yml/badge.svg?branch=main"></a>
  <img alt="Stack" src="https://img.shields.io/badge/stack-Django%206%20%C2%B7%20React%2019-0b7285.svg">
  <a href=".github/CONTRIBUTING.md"><img alt="PRs welcome" src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg"></a>
</p>

</div>

---

Space Works started inside the **TinkerSpace Kochi** community, from a simple need: make it easy for a
makerspace to know **what tools and equipment exist, who borrowed what, what's available, and how
every loan and print job moves from request to done** — with enough traceability that accountability
for shared gear is never a guessing game. It's built by makers, for makers: run it at your space, fork it, remix it, or use it as
a starting point. If your community works differently, make it your own.

One deployment can host **many makerspaces** (tenants). Each owns its inventory, public URL, staff,
Telegram group, QR namespace, and audit scope — fully isolated from the others.

## Features

- **Public catalog** — browse by makerspace and category, request to borrow, and (when enabled)
  **QR self-checkout/return** for present members with photo evidence.
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

Space Works runs entirely through Docker Compose — it brings up **PostgreSQL, Redis, MinIO storage, the
Celery worker/beat, and database migrations** and wires them to the app for you (the images don't bake
in any addresses; the compose file passes them in). Pick one path:

**Path 1 — Guided setup (easiest; builds from source).** One script generates all secrets, writes
`.env`, builds everything, and creates your first admin + makerspace:

```bash
git clone https://github.com/SpaceWorks-HQ/SpaceWorks.git
cd SpaceWorks
bash setup.sh                                          # macOS / Linux
powershell -ExecutionPolicy Bypass -File setup.ps1     # Windows
```

It prints your URL and login when it finishes and offers to install seven-day, backup-first production update checks. Super Admins can control
automatic or manual installation from **Platform settings -> Software updates**. (Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).)

**Path 2 — Prebuilt images (no local build).** Pull the two published images and start the stack —
after `cp .env.example .env` (fill in the few values it asks for):

```bash
export MAKERSPACE_IMAGE_TAG=latest        # or pin a release, e.g. 0.5.1-main.42.a1b2c3d4e5f6
docker compose -f docker-compose.prod.yml up -d
```

This pulls **`ghcr.io/spaceworks-hq/spaceworks-backend`** + **`ghcr.io/spaceworks-hq/spaceworks-frontend`** and brings up the
full stack automatically.

## Documentation

| I want… | Go to |
|---|---|
| A **plain-language, non-technical** walkthrough | **[docs/setup-for-makerspaces.md](docs/setup-for-makerspaces.md)** |
| **Production** reference (env vars, TLS, upgrades, releases) | **[docs/self-hosting.md](docs/self-hosting.md)** |
| **Advanced** config (Telegram, HMAC, Supabase, cron) | **[.github/ADVANCED.md](.github/ADVANCED.md)** |
| **Develop / contribute** (run from source, tests, releases) | **[.github/DEVELOPMENT.md](.github/DEVELOPMENT.md)** |

## Roadmap

Space Works 0.5 is focused on reliable self-hosting and complete makerspace operations:

- automatic, backup-first updates from every successful `main` release;
- stable public, member, staff, and superadmin workflows across the full module set;
- continued accessibility, mobile, reporting, and operational resilience work.

Current work and shipped changes are tracked in
[GitHub issues](https://github.com/SpaceWorks-HQ/SpaceWorks/issues),
[pull requests](https://github.com/SpaceWorks-HQ/SpaceWorks/pulls), and the release notes. The running
product intentionally does not expose a separate roadmap page.

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
| **Public** | Browse, request, self-checkout/return eligible QR tools (member presence + photo evidence) | Anything authenticated |

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
Guided installs can receive each successful `main` release automatically with a backup and readiness
check. If deployment fails, the application containers return to the previous retained release. Run
`scripts/update.sh --force` (macOS/Linux) or `scripts/update.ps1 -Force` (Windows) for an immediate
update; see **[docs/self-hosting.md](docs/self-hosting.md)** for scheduling, pinning, TLS, and recovery.

**No server of your own?** Space Works is multi-tenant — partner with a nearby makerspace to run your space
as a tenant on their instance. **Prefer managed Postgres?** Point `DATABASE_URL` at any managed
Postgres (e.g. Supabase) and host the app anywhere; a fully-managed free-tier path is documented in
**[docs/supabase-deployment.md](docs/supabase-deployment.md)** (best for demo/pilot, not dependable
production).

## Tech stack

Django 6 + DRF · React 19 + Vite 8 + Tailwind CSS 4 + TypeScript (TanStack Query v5) · PostgreSQL 16 ·
Celery + Redis · MinIO (S3-compatible) · django-unfold admin · drf-spectacular / OpenAPI. Delivered as
two Docker images (`spaceworks-backend`, `spaceworks-frontend`); everything else is official upstream images.

## Contributing

Space Works is a collaborative project for the makerspace community, and **contributors are very welcome** —
code, docs, translations, or just running it at your space and reporting what's rough. See
**[.github/CONTRIBUTING.md](.github/CONTRIBUTING.md)**. **No CLA is required** — by opening a pull
request you agree your contribution is offered under the project's AGPL-3.0-or-later license
(inbound = outbound); merged contributors are credited in
[.github/CONTRIBUTORS.md](.github/CONTRIBUTORS.md).

## License

Space Works is **free and open source software**, licensed under the
**[GNU Affero General Public License v3](LICENSE)** (`AGPL-3.0-or-later`).

You are free to use, study, share, and modify Space Works — for **any** purpose, commercial or
noncommercial — subject to the AGPL. Because the AGPL is a **network copyleft** license: if you run
a modified version and let users interact with it over a network, you must offer those users the
corresponding source code of your modified version under the same license.

## Contributors

Thanks to **everyone** who has contributed to Space Works — code, docs, bug reports, or running it at their
space. The wall below is pulled live from this repository's
[GitHub contributor graph](https://github.com/SpaceWorks-HQ/SpaceWorks/graphs/contributors) and
shows **all** contributors — bots and automation included, no filtering:

[![Contributors](https://contrib.rocks/image?repo=SpaceWorks-HQ/SpaceWorks&max=100)](https://github.com/SpaceWorks-HQ/SpaceWorks/graphs/contributors)

<sub>Contributor image by [contrib.rocks](https://contrib.rocks).</sub>
