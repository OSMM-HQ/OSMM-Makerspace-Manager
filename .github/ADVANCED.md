# OSMM — Advanced configuration

Optional configuration for operators. None of this is needed for a standard self-hosted install —
the [Quick start](../README.md#quick-start-run-it) covers the common case. See
[docs/self-hosting.md](../docs/self-hosting.md) for the full environment reference.

## Telegram alerts & accept/reject callbacks

Set the group chat ID + bot token in the staff `API clients → Integration settings` panel; set
`TELEGRAM_WEBHOOK_SECRET` for webhook callbacks. The bot token is encrypted at rest with
`API_CLIENT_ENC_KEY` (a Fernet key).

## Server-to-server HMAC clients

Optional signed API access for backend integrations (disabled unless `HMAC_CLIENT_ID` + `HMAC_SECRET`
are set). Browser frontends must use publishable keys + `/api/v1/bootstrap`, never HMAC secrets.

## Security hardening

django-axes admin-login lockout, login + public-submit throttles, honeypot, and TLS headers
(`ENABLE_HTTPS`). A `pip-audit` CI job guards dependencies.

## Managed-Postgres / Supabase mode

`MANAGED_POSTGRES`, `STORAGE_PRESIGN_METHOD`, `CONN_MAX_AGE`, `DISABLE_SERVER_SIDE_CURSORS`,
`CRON_SECRET` (all default to self-hosted behavior). See
[docs/supabase-deployment.md](../docs/supabase-deployment.md).

## Scheduled return reminders

Run `manage.py send_return_reminders` from cron, or (when you can't schedule a command, e.g. on
Supabase) `POST /api/v1/internal/cron/return-reminders` with an `X-Cron-Secret` header; the endpoint
404s until `CRON_SECRET` is set.
