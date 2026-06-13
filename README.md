# TinkerSpace Inventory Manager

Multi-tenant makerspace inventory manager with a Django API and Vite React frontend.

## Local Setup

### 1. Start Postgres

```powershell
docker compose up -d db
```

### 2. Configure The Backend

Copy the backend environment template:

```powershell
Copy-Item backend\.env.example backend\.env
```

Set these required values in `backend\.env`:

```env
SECRET_KEY=replace-with-a-long-random-secret
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://tinker:tinker@localhost:5432/tinkerspace
CORS_ALLOWED_ORIGINS=http://localhost:5000,http://localhost:5173
```

Install dependencies, run migrations, and seed demo data:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

The API will run at `http://localhost:8000/api`.

### 3. Configure The Frontend

Copy the frontend environment template:

```powershell
Copy-Item frontend\.env.example frontend\.env
```

Set:

```env
VITE_API_URL=http://localhost:8000/api
```

Install dependencies and start Vite:

```powershell
cd frontend
npm install
npm run dev
```

The frontend will run at `http://localhost:5000`.

## Public Makerspace Switching

The public frontend automatically lists makerspaces that have `public_inventory_enabled=True`.

```text
Public directory: http://localhost
Makerspace inventory: http://localhost/m/<makerspace-slug>
```

Create or update makerspaces in the backend admin. Each public makerspace must have a unique `slug`; that slug is how the public URL stays tied to the correct makerspace.

## Docker Hosting

The repo includes Docker support for:

- `db`: Postgres 16
- `backend`: Django API served by Gunicorn
- `frontend`: Vite production build served by Nginx, with `/api/` proxied to the backend

### Run Everything With Docker

From the repo root:

```powershell
docker compose up --build
```

Open:

```text
Frontend: http://localhost
Backend API through frontend proxy: http://localhost/api
Backend API direct container port: http://localhost:8001/api
Backend admin direct container port: http://localhost:8001/admin/
```

The backend container automatically runs:

```text
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

### Seed Demo Data In Docker

After the containers are running:

```powershell
docker compose exec backend python manage.py seed_demo
```

### Stop Docker

```powershell
docker compose down
```

To remove the Postgres volume too:

```powershell
docker compose down -v
```

### Docker Environment

For local Docker, Compose provides defaults. For hosting, set these environment variables in your deployment platform or in a root `.env` file next to `docker-compose.yml`:

```env
SECRET_KEY=replace-with-a-long-random-secret
DEBUG=False
ALLOWED_HOSTS=your-domain.com,localhost,127.0.0.1,backend
DATABASE_URL=postgres://tinker:tinker@db:5432/tinkerspace
CORS_ALLOWED_ORIGINS=https://your-domain.com
VITE_API_URL=/api
```

For production self-hosting from published images, see [docs/self-hosting.md](docs/self-hosting.md).

If enabling HMAC for server-to-server clients, set backend values only:

```env
HMAC_CLIENT_ID=web-client
HMAC_SECRET=replace-with-a-long-random-shared-secret
```

For a hosted domain, point traffic to the frontend container on port `80`. Nginx serves the frontend and forwards `/api/` to the backend container.

## Server-To-Server HMAC Link

The backend supports optional HMAC request validation for server-side API clients. It is disabled unless both `HMAC_CLIENT_ID` and `HMAC_SECRET` are set.

Backend `backend\.env`:

```env
HMAC_CLIENT_ID=web-client
HMAC_SECRET=replace-with-a-long-random-shared-secret
HMAC_MAX_CLOCK_SKEW_SECONDS=300
HMAC_PROTECTED_PATH_PREFIXES=/api/public/
```

Server clients sign each GET request with:

```text
GET
<path-and-query>
<unix-timestamp>
<body>
```

The backend checks `X-Client-Id`, `X-Timestamp`, and `X-Signature`.

Important: browser frontends must use publishable keys and `/api/v1/bootstrap`, not HMAC secrets. Any value compiled into JavaScript is public.

## Telegram Setup

1. Open Telegram and start a chat with `@BotFather`.
2. Run `/newbot`, follow the prompts, and copy the generated bot token.
3. Add the bot to the target Telegram group.
4. Send any message in the group.
5. Call `https://api.telegram.org/bot<token>/getUpdates` and copy the group `chat.id` value. Supergroups usually start with `-100`.
6. In the staff `/admin` UI, open `API clients` -> `Integration settings`.
7. Enter the Telegram group chat ID and bot token, save, then click `Send Telegram test alert`.

The group chat ID is configuration, not a secret. The bot token is sensitive and is encrypted at rest with `API_CLIENT_ENC_KEY`, the same Fernet key used for API client secrets and makerspace SMTP passwords. Generate it with:

```env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

For Telegram accept/reject webhook callbacks, also set `TELEGRAM_WEBHOOK_SECRET` in the backend environment and configure Telegram's webhook secret token to the same value.

## Supabase Setup

The backend uses Django with Postgres. Supabase can be used as the hosted Postgres database by pointing `DATABASE_URL` at the Supabase connection string.

1. Create a Supabase project.
2. In Supabase, open Project Settings, then Database.
3. Copy the Postgres connection string. For production deployments, prefer the pooled connection string if your host has connection limits.
4. Replace the password placeholder in the connection string with your database password.
5. Set `DATABASE_URL` in `backend\.env` or your deployment environment.
6. Add `?sslmode=require` if your connection string does not already require SSL.
7. Run backend migrations against the Supabase database:

```powershell
cd backend
python manage.py migrate
```

Example:

```env
DATABASE_URL=postgres://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require
```

If you later add Supabase Auth or Storage, also add the public project URL and anon key to the frontend environment, and keep service-role keys only on the backend.

Suggested environment names:

```env
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
```

Never expose `SUPABASE_SERVICE_ROLE_KEY` in the frontend.

## Tests

Run backend tests:

```powershell
cd backend
pytest
```
