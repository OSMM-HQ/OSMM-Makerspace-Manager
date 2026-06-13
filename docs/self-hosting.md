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
MAKERSPACE_IMAGE_TAG=latest
```

Optional image overrides:

```env
MAKERSPACE_BACKEND_IMAGE=ghcr.io/shaan-shoukath/makerspace-manager-backend
MAKERSPACE_FRONTEND_IMAGE=ghcr.io/shaan-shoukath/makerspace-manager-frontend
```

### Build from source (no published images)

Until the GHCR images are published publicly, build locally with the build overlay:

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.build.yml up -d --build
```

For a guided first run that generates secrets and `.env` for you, use the `setup.sh` / `setup.ps1`
scripts at the repo root (see [setup-for-makerspaces.md](setup-for-makerspaces.md)).

> The frontend container's nginx proxies `/api/`, `/admin/`, `/static/`, and the docs routes to the
> backend, so the **single published port (80)** serves the public app, the Super Admin Django
> admin, and Swagger. The backend port is intentionally not exposed.

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
MAKERSPACE_IMAGE_TAG=v0.2.0
```

Then run:

```powershell
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

The backend container runs migrations on startup. Keep a database backup before changing versions.

Manual dependency audit: `pip install pip-audit && pip-audit -r backend/requirements.txt`.

## HTTPS & security hardening

TLS-dependent settings are **env-gated, not `DEBUG`-gated**, so the default HTTP-behind-nginx stack
works out of the box. For a real domain with TLS:

1. Put a reverse proxy that terminates TLS in front of the frontend container (e.g. Caddy, or
   nginx/Traefik with a certificate) and have it forward `X-Forwarded-Proto: https`.
2. Set `ENABLE_HTTPS=true` — this turns on `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`,
   `CSRF_COOKIE_SECURE`, and HSTS.
3. Set `CSRF_TRUSTED_ORIGINS=https://your-domain.org` so admin/login POSTs are accepted.

> **Important:** when `ENABLE_HTTPS=true`, the frontend container's HTTP port must be reachable
> **only through your TLS proxy** — do not publish it publicly (bind it to the proxy or a private
> network). The frontend honors a forwarded `X-Forwarded-Proto`, so a client that could reach the
> raw HTTP port directly could otherwise spoof `https` and bypass the SSL redirect. (With the
> default `ENABLE_HTTPS=false` there is no redirect, so this does not apply.)

Always-on protections (any transport): `django-axes` locks out brute-force admin logins
(`AXES_FAILURE_LIMIT`, keyed by ip+username), a scoped throttle limits the JWT login endpoint, the
public submit endpoint has its own anti-spam throttle + a honeypot, and a Content-Security-Policy is
sent on every response. The Django admin is restricted to active superusers only.

Secrets (`SECRET_KEY`, `API_CLIENT_ENC_KEY`, makerspace Telegram bot tokens, makerspace SMTP
passwords) live only in the backend. `API_CLIENT_ENC_KEY` is the Fernet key that encrypts the
per-makerspace integration secrets at rest — **back it up and do not rotate it casually**, or
previously stored tokens/passwords can no longer be decrypted.

## Environment reference

| Variable | Required | Purpose |
|---|---|---|
| `POSTGRES_PASSWORD` | yes | Database password (also used to build `DATABASE_URL`) |
| `SECRET_KEY` | yes | Django cryptographic secret |
| `ALLOWED_HOSTS` | yes | Comma-separated hostnames the backend will serve |
| `DATABASE_URL` | no | Overrides the default Postgres URL (e.g. point at Supabase) |
| `CORS_ALLOWED_ORIGINS` | no | Browser origins allowed to call the API |
| `API_CLIENT_ENC_KEY` | recommended | Fernet key encrypting integration secrets at rest |
| `ENABLE_HTTPS` | no (default false) | Turns on SSL redirect, Secure cookies, HSTS |
| `CSRF_TRUSTED_ORIGINS` | when HTTPS | `https://` origin(s) trusted for admin/login POST |
| `AXES_FAILURE_LIMIT` | no (default 5) | Failed admin logins before lockout |
| `HTTP_PORT` | no (default 80) | Published frontend port |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL` | no | Global fallback SMTP (per-makerspace SMTP overrides it) |

## Backups

All data lives in the `makerspace_manager_pgdata` Docker volume. Back it up before upgrades:

```bash
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U makerspace makerspace_manager > backup-$(date +%F).sql
```

Also keep a copy of your `.env` (it holds `API_CLIENT_ENC_KEY`, without which encrypted integration
secrets are unrecoverable).

## Tenant Frontends

One backend can serve **many makerspaces**. A makerspace without its own server can be hosted as an
additional tenant on another makerspace's instance — each tenant gets its own makerspace record,
public URL/slug, branding, and (optionally) its own frontend origin, all isolated by makerspace
scoping. Register a frontend per tenant so CORS and bootstrap resolve correctly.

Browser frontends must use publishable configuration only. Do not place HMAC secrets in JavaScript bundles.

Use `GET /api/v1/bootstrap?tenant=<tenant-token-or-public-code>` or `GET /api/v1/bootstrap?slug=<makerspace-slug>` to load:

- makerspace identity
- frontend type
- enabled modules and workflows
- theme and branding
- publishable public API hints

Registered tenant frontend origins and makerspace CORS origins are used for per-tenant browser access.
