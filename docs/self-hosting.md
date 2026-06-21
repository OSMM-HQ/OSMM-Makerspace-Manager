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
MINIO_ROOT_USER=replace-with-a-random-access-key
MINIO_ROOT_PASSWORD=replace-with-a-long-random-secret
AWS_S3_PUBLIC_ENDPOINT_URL=https://files.inventory.example.org
MINIO_CORS_ALLOWED_ORIGINS_JSON=["https://inventory.example.org"]
MAKERSPACE_IMAGE_TAG=latest
```

Optional image overrides:

```env
MAKERSPACE_BACKEND_IMAGE=ghcr.io/shaan-shoukath/osmm-backend
MAKERSPACE_FRONTEND_IMAGE=ghcr.io/shaan-shoukath/osmm-frontend
```

### Build from source (no published images)

Until the GHCR images are published publicly, build locally with the build overlay:

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.build.yml up -d --build
```

For a guided first run that generates secrets and `.env` for you, use the `setup.sh` / `setup.ps1`
scripts at the repo root (see [setup-for-makerspaces.md](setup-for-makerspaces.md)).

> The frontend container's nginx proxies `/api/`, `/static/`, and the docs routes to the backend.
> The **single published port (80)** serves the public app, the React staff console at `/admin`,
> and Swagger. The Django control plane is mounted at `/control/` on the backend and is
> intentionally **not exposed** on the public frontend port; access it only through direct backend
> access.

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

TLS-dependent settings are **env-gated, not `DEBUG`-gated**, so the default HTTP stack works out of
the box. The default frontend nginx does **not** trust inbound `X-Forwarded-Proto`; it forwards only
its own scheme to Django.

For a real domain with automatic TLS, use the Caddy overlay:

```env
PUBLIC_DOMAIN=inventory.example.org
CSRF_TRUSTED_ORIGINS=https://inventory.example.org
AWS_S3_PUBLIC_ENDPOINT_URL=https://files.inventory.example.org
MINIO_CORS_ALLOWED_ORIGINS_JSON=["https://inventory.example.org"]
```

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.tls.yml --profile tls up -d
```

The overlay enables `ENABLE_HTTPS=true` and `TRUST_X_FORWARDED_PROTO=true` for the backend. Caddy is
then the trusted TLS boundary: `/api`, `/static`, and docs paths go directly to Django with
`X-Forwarded-Proto: https`, while the React app goes to the frontend container. Keep any direct
backend/frontend HTTP ports private when the TLS overlay is active.



Always-on protections (any transport): `django-axes` locks out brute-force admin logins
(`AXES_FAILURE_LIMIT`, keyed by ip+username), a scoped throttle limits the JWT login endpoint, the
public submit endpoint has its own anti-spam throttle + a honeypot, and a Content-Security-Policy is
sent on every response. The Django control plane at `/control/` is restricted to active
superusers only and must be reached through direct backend access, never through the public
frontend port.

Secrets (`SECRET_KEY`, `API_CLIENT_ENC_KEY`, makerspace Telegram bot tokens, makerspace SMTP
passwords) live only in the backend. `API_CLIENT_ENC_KEY` is the Fernet key that encrypts the
per-makerspace integration secrets at rest â€” **back it up and do not rotate it casually**, or
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
| `MINIO_ROOT_USER` | yes | MinIO/S3 access key used by the backend |
| `MINIO_ROOT_PASSWORD` | yes | MinIO/S3 secret key used by the backend |
| `AWS_STORAGE_BUCKET_NAME` | no (default `evidence`) | Private object-storage bucket for evidence and print files |
| `PUBLIC_IMAGE_BUCKET` | no (default `public-images`) | Anonymous-read bucket for public item photos and makerspace logo/cover images |
| `PUBLIC_IMAGE_BASE_URL` | yes for public images | Browser public base URL for `PUBLIC_IMAGE_BUCKET` (for example `https://files.inventory.example.org/public-images`) |
| `PUBLIC_IMAGE_MAX_BYTES` | no (default `5242880`) | Maximum public image upload size |
| `PUBLIC_IMAGE_URL_TTL_SECONDS` | no (default `300`) | Presigned upload URL lifetime for public images |
| `AWS_S3_ENDPOINT_URL` | no (default `http://minio:9000`) | Backend-to-MinIO endpoint inside Compose |
| `AWS_S3_PUBLIC_ENDPOINT_URL` | yes for uploads | Browser-reachable MinIO/S3 endpoint used in presigned URLs |
| `MINIO_CORS_ALLOWED_ORIGINS_JSON` | yes for uploads | JSON array of frontend origins allowed to POST/GET objects |
| `ENABLE_HTTPS` | no (default false) | Turns on SSL redirect, Secure cookies, HSTS |
| `TRUST_X_FORWARDED_PROTO` | no (default false) | Trusts `X-Forwarded-Proto` only for the TLS proxy overlay |
| `CSRF_TRUSTED_ORIGINS` | when HTTPS | `https://` origin(s) trusted for login POSTs |
| `AXES_FAILURE_LIMIT` | no (default 5) | Failed admin logins before lockout |
| `HTTP_PORT` | no (default 80) | Published frontend port |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL` | no | Global fallback SMTP (per-makerspace SMTP overrides it) |
| `MANAGED_POSTGRES` | no (default `False`) | `True` on managed Postgres (Supabase): purge suspends immutability triggers via a custom GUC instead of `session_replication_role` (which needs superuser) |
| `CONN_MAX_AGE` | no (default `0`) | Persistent DB connection lifetime; keep `0` on the Supabase transaction pooler |
| `DISABLE_SERVER_SIDE_CURSORS` | no (default `False`) | Set `True` on the Supabase transaction pooler (no server-side cursors) |
| `STORAGE_PRESIGN_METHOD` | no (default `post`) | `put` for Supabase Storage presigned PUT uploads (server re-validates size at attach) |
| `CRON_SECRET` | no (default empty) | Enables `POST /api/v1/internal/cron/return-reminders` (header `X-Cron-Secret`); 404s while unset |

> **Supabase free-tier deployment** (managed Postgres + Storage, env-toggled, demo/pilot scope):
> see **[supabase-deployment.md](supabase-deployment.md)** for the full runbook. All five vars
> above default to the self-hosted behavior, so this Compose stack is unaffected unless you set them.

## Object Storage

Production Compose includes MinIO because the backend stores evidence photos and 3D-print files in
S3-compatible object storage by default. The backend talks to MinIO at `http://minio:9000`; browsers
use `AWS_S3_PUBLIC_ENDPOINT_URL` in presigned upload/download URLs, so that value must be reachable
from staff/requester browsers.

Public catalog images use a separate `PUBLIC_IMAGE_BUCKET` that is anonymous-readable by design.
The bundled Compose bootstrap creates it, sets `download` policy, and applies the same upload CORS
policy. Keep evidence and print files in the private `AWS_STORAGE_BUCKET_NAME`; only item photos and
makerspace logo/cover images belong in the public bucket.

For HTTPS deployments, put MinIO behind the same TLS proxy as the frontend, for example:

```env
AWS_S3_PUBLIC_ENDPOINT_URL=https://files.inventory.example.org
MINIO_CORS_ALLOWED_ORIGINS_JSON=["https://inventory.example.org"]
```

If you expose MinIO directly on a LAN during a local pilot, set `AWS_S3_PUBLIC_ENDPOINT_URL` to the
server address and port that browsers can reach, for example `http://192.168.1.20:9000`. The MinIO
console binds to `127.0.0.1:9001` by default; keep it private or put it behind authenticated VPN/admin
access.

## Backups

Operational data lives in Postgres and object files live in the `minio_data` Docker volume. Back up
both before upgrades:

```bash
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U makerspace makerspace_manager > backup-$(date +%F).sql

mkdir -p backups
docker compose -f docker-compose.prod.yml run --rm --entrypoint sh \
  -v "$PWD/backups:/backup" \
  minio \
  -c 'tar -czf /backup/minio-$(date +%F).tgz -C /data .'
```

Also keep a copy of your `.env` (it holds `API_CLIENT_ENC_KEY`, without which encrypted integration
secrets are unrecoverable, and the MinIO credentials needed to read object backups).

Restore order is database first, then object files. Stop the stack, restore the Postgres dump into the
`db` service, unpack the MinIO archive into the `minio_data` volume, then start the stack and check
`/api/v1/health/readiness/`.

## Tenant Frontends

One backend can serve **many makerspaces**. A makerspace without its own server can be hosted as an
additional tenant on another makerspace's instance â€” each tenant gets its own makerspace record,
public URL/slug, branding, and (optionally) its own branded domain, all isolated by makerspace
scoping. To give a tenant its own branded site, set its **Custom domain**
(`Makerspace.frontend_domain`) in the staff console Settings tab; that single field drives CORS,
bootstrap resolution, and the staff-auth allowlist. See `docs/single-tenant-frontend.md`.

Browser frontends must use publishable configuration only. Do not place HMAC secrets in JavaScript bundles.

Use `GET /api/v1/bootstrap?tenant=<public-code>` or `GET /api/v1/bootstrap?slug=<makerspace-slug>`
(or simply serve the branded site from its `frontend_domain`, which bootstrap resolves by origin) to load:

- makerspace identity
- enabled modules and workflows
- theme and branding
- publishable public API hints

A makerspace's `frontend_domain` and its `cors_allowed_origins` (API-client origins) are used for
per-tenant browser access; only the `frontend_domain` origin may hold a staff session.
