# Self-Hosting Guide

This project is Docker-first for operators who do not want to build Django or Vite locally.

## Production Compose

Use the production Compose file when deploying published images:

```powershell
Copy-Item .env.example .env
docker compose -f docker-compose.prod.yml up -d
```

Set these values before first boot:

```env
POSTGRES_PASSWORD=replace-with-a-strong-password
SECRET_KEY=replace-with-a-long-random-secret
ALLOWED_HOSTS=inventory.example.org
CORS_ALLOWED_ORIGINS=https://inventory.example.org
TINKERSPACE_IMAGE_TAG=latest
```

Optional image overrides:

```env
TINKERSPACE_BACKEND_IMAGE=ghcr.io/tinkerspace/inventory-manager-backend
TINKERSPACE_FRONTEND_IMAGE=ghcr.io/tinkerspace/inventory-manager-frontend
```

## First Run

Create the first superadmin and makerspace:

```powershell
docker compose -f docker-compose.prod.yml exec backend python manage.py setup_instance `
  --username admin `
  --email admin@example.org `
  --password "replace-with-a-strong-password" `
  --makerspace-name "My Makerspace"
```

The command is idempotent. It creates missing records and upgrades the named user to a superadmin if needed.

## Health Checks

Backend:

```text
GET /api/v1/health/
GET /api/v1/health/readiness/
```

The Compose files include health checks for Postgres, backend readiness, and frontend HTTP serving.

## Scheduled Jobs

Return reminder emails are sent by a management command. Schedule it every 15-60 minutes with cron, systemd timers, Windows Task Scheduler, or your hosting platform's scheduler:

```powershell
docker compose -f docker-compose.prod.yml exec backend python manage.py send_return_reminders
```

The command is idempotent. It only sends reminders for issued or partially returned requests whose `return_due_at` is in the past and whose reminder has not already been sent. Requests returned before the due time are skipped.

## Upgrades

Pin a release tag for stable deployments:

```env
TINKERSPACE_IMAGE_TAG=v0.2.0
```

Then run:

```powershell
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

The backend container runs migrations on startup. Keep a database backup before changing versions.

## Tenant Frontends

Browser frontends must use publishable configuration only. Do not place HMAC secrets in JavaScript bundles.

Use `GET /api/v1/bootstrap?tenant=<tenant-token-or-public-code>` or `GET /api/v1/bootstrap?slug=<makerspace-slug>` to load:

- makerspace identity
- frontend type
- enabled modules and workflows
- theme and branding
- publishable public API hints

Registered tenant frontend origins and makerspace CORS origins are used for per-tenant browser access.
