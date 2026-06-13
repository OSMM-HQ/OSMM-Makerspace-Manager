# Makerspace Manager

Open-source, multi-tenant **hardware-loan manager for makerspaces**. The public can browse
a makerspace's inventory and request to borrow tools; staff issue and return that hardware with
full traceability — every handover produces evidence (QR scans + photos + remarks + an
append-only audit log) so accountability for lost or damaged hardware is never ambiguous.

One deployment can host many makerspaces (tenants). Each owns its inventory, public URL,
staff, Telegram group, QR namespace, and audit scope.

- **Public** → React catalog: pick a makerspace, browse by category, request hardware. No login.
- **Super Admin** → the **Django admin** is the sole superadmin control plane: create makerspaces
  and run every operation (requests, transfers, stocktake, QR, printing) as audited admin actions.
- **All other staff** → the **React staff console** (JWT login). They have **no Django admin access**.

## Why this exists

The goal is to make it **easy for makerspaces to log and track their stuff**, and to give the
whole **community transparent access** to what's available to borrow — without spreadsheets or
guesswork. It's open source and built to be run by the community, for the community. If you care
about makerspaces and want to help, **volunteers and contributors are very welcome** — whether
you write code, docs, translations, or just run it at your space and report what's rough. See
[CONTRIBUTING.md](CONTRIBUTING.md).

---

## Roles & permissions

Access is scoped per makerspace and per action. Super Admin is global; every other role is a
per-makerspace membership.

| Role | Works in | Can do | Cannot do |
|---|---|---|---|
| **Super Admin** | Django admin only | Everything, globally: create/manage makerspaces, all hardware/printing/ops actions, staff, settings, API clients, audit | — |
| **Space Manager** | React staff console | Full hardware lifecycle for their space (accept/reject, assign box, issue, return, evidence, QR), direct handouts, manage inventory & staff & settings | Other makerspaces; Django admin |
| **Inventory Manager** | React staff console | Full hardware lifecycle + inventory edit + QR + evidence + audit for their space | Printing, staff, makerspace settings; Django admin |
| **Guest Admin** | React staff console | Issue accepted requests + process returns (evidence/QR/remark/audit) | Accept/reject, edit inventory, manage QR, direct handouts; Django admin |
| **Print Manager** | React staff console | 3D-printing request lifecycle (accept/start/complete/fail), printers & spools | Hardware lifecycle, inventory, staff; Django admin |
| **Public** | React catalog | Browse public inventory, submit borrow requests | Anything authenticated |

> **These roles are defined by the system, not by any user.** A Space Manager (or anyone else)
> cannot invent new roles or grant themselves extra powers — they can only assign people to the
> existing roles within their own makerspace. What each role can and cannot do is fixed in the
> platform's permission rules, which keeps every makerspace consistent and accountable.

Two architectural rules are load-bearing:

1. **The Request Workflow module is the single source of truth for state transitions.** The web
   admin, the React console, and Telegram callbacks all route through the same workflow services —
   no module mutates `HardwareRequest.status` directly.
2. **The Inventory Availability module owns all quantity math.** Reserve / issue / return /
   mark-lost all flow through it; availability never goes below zero.

**Stack:** Django 5 + DRF backend · React 18 + Vite + TypeScript frontend (TanStack Query) ·
PostgreSQL 16 · django-unfold admin · drf-spectacular / OpenAPI.

---

## Hosting

**The primary objective is to self-host inside the makerspace, on a local server.** Your data,
your network, no third party. If a makerspace has no local server to run Postgres, use a managed
Postgres (Supabase) instead and host the app anywhere.

### Option A — Self-host locally (recommended)

**Not a developer?** Follow the plain-language, step-by-step guide:
**[docs/setup-for-makerspaces.md](docs/setup-for-makerspaces.md)**. After installing Docker
Desktop and downloading this project, you run **one** setup script that asks a few questions and
does the rest:

```bash
# macOS / Linux
bash setup.sh
```
```powershell
# Windows (right-click setup.ps1 → Run with PowerShell, or:)
powershell -ExecutionPolicy Bypass -File setup.ps1
```

It generates all secrets, writes your `.env`, builds and starts everything, and creates your first
admin + makerspace. When it finishes it prints your URL and login.

**Prefer to drive Docker yourself?** The same production stack, built from source:

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.build.yml up -d --build
```

| Surface | URL |
|---|---|
| Public frontend | `http://localhost` |
| API (via frontend proxy) | `http://localhost/api` |
| API (direct container) | `http://localhost:8001/api` |
| Django admin (superadmin) | `http://localhost:8001/admin/` |

Seed demo data and create the first superadmin / makerspace:

```bash
docker compose exec backend python manage.py seed_demo
# or, for a real instance:
docker compose exec backend python manage.py setup_instance
```

For production from published images (env vars, TLS, reverse proxy), see
**[docs/self-hosting.md](docs/self-hosting.md)**.

> 📦 **One-command hosting guide: _link coming soon_** (will point to the published image + compose bundle).

Set `ENABLE_HTTPS=true` only when a reverse proxy terminates real TLS and forwards
`X-Forwarded-Proto: https`; otherwise the default HTTP-behind-nginx setup is correct.

### Option B — No local server? Partner with another makerspace first

This app is **multi-tenant**: one backend can host many makerspaces, each with its own public URL,
branding, and frontend. So if you don't have a server, **reach out to a nearby makerspace that
does** — they can host your makerspace as an additional tenant on their instance. Most makers are
happy to help a fellow space, and it's a natural way for them to contribute to the project. You get
your own catalog and admin; they run one shared backend.

### Option C — Still not possible? Supabase Postgres

The backend is plain Django + Postgres, so any managed Postgres works. Point `DATABASE_URL` at a
Supabase connection string and host the app on any platform.

1. Create a Supabase project → **Project Settings → Database** → copy the connection string
   (prefer the **pooled** string if your host has connection limits).
2. Replace the password placeholder and append `?sslmode=require` if not already present.
3. Set `DATABASE_URL` in the backend environment and run migrations:

```bash
cd backend && python manage.py migrate
```

```env
DATABASE_URL=postgres://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require
```

If you later adopt Supabase Auth/Storage, keep `SUPABASE_SERVICE_ROLE_KEY` on the **backend only** —
never expose it to the frontend.

---

## Development

### 1. Database

```bash
docker compose up -d db
```

### 2. Backend (`backend/`)

```bash
cd backend
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1   |   *nix: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set SECRET_KEY, DATABASE_URL, CORS_ALLOWED_ORIGINS
python manage.py migrate
python manage.py seed_demo
python manage.py runserver      # http://localhost:8000
```

Minimum `backend/.env` for local dev:

```env
SECRET_KEY=replace-with-a-long-random-secret
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://makerspace:makerspace@localhost:5432/makerspace_manager
CORS_ALLOWED_ORIGINS=http://localhost:5000,http://localhost:5173
```

### 3. Frontend (`frontend/`)

```bash
cd frontend
cp .env.example .env            # VITE_API_URL=http://localhost:8000/api
npm install
npm run dev                     # http://localhost:5000
```

- Public catalog: `http://localhost:5000` → pick a makerspace, or go straight to `/m/<slug>`
  (the demo seed creates `/m/makerspace`).
- API docs (Swagger): `http://localhost:8000/docs/` · schema at `/schema/`.

### Tests

```bash
cd backend && pytest
```

---

## Advanced configuration

- **Telegram alerts & accept/reject callbacks** — set the group chat ID + bot token in the staff
  `API clients → Integration settings` panel; set `TELEGRAM_WEBHOOK_SECRET` for webhook callbacks.
  The bot token is encrypted at rest with `API_CLIENT_ENC_KEY` (a Fernet key).
- **Server-to-server HMAC clients** — optional signed API access for backend integrations
  (disabled unless `HMAC_CLIENT_ID` + `HMAC_SECRET` are set). Browser frontends must use
  publishable keys + `/api/v1/bootstrap`, never HMAC secrets.
- **Security hardening** — django-axes admin-login lockout, login + public-submit throttles,
  honeypot, and TLS headers (`ENABLE_HTTPS`). A `pip-audit` CI job guards dependencies.

See [docs/self-hosting.md](docs/self-hosting.md) for the full environment reference.

---

## Contributing

Contributions are welcome. Please read **[CONTRIBUTING.md](CONTRIBUTING.md)** for the development
workflow, branch/commit conventions, testing expectations, and how to open a pull request.
