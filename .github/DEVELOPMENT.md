# Space Works — Development

Running Space Works from source for local development or contributing. If you just want to **run** Space Works,
use the [Quick start](../README.md#quick-start-run-it) instead — you don't need any of this.

**Toolchain prerequisites:** Python 3.12+ and Node 20.19+ (or 22.12+, for Vite 8). The Docker path
bundles everything, so these only matter when you run the backend/frontend directly.

## 0. Get the code

```bash
git clone https://github.com/SpaceWorks-HQ/SpaceWorks.git
cd SpaceWorks
```

## 1. Database

```bash
docker compose up -d db
```

## 2. Backend (`backend/`)

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

## 3. Frontend (`frontend/`)

```bash
cd frontend
cp .env.example .env            # VITE_API_URL=http://localhost:8000/api
npm install
npm run dev                     # http://localhost:5000
```

- Public catalog: `http://localhost:5000` → pick a makerspace, or go straight to `/m/<slug>`
  (the demo seed creates `/m/makerspace`).
- API docs (Swagger): `http://localhost:8000/docs/` · schema at `/schema/`.

> The frontend Docker image builds on `node:22-alpine` (npm 10). If you regenerate
> `frontend/package-lock.json` on a newer Node/npm, do it inside that image so the lockfile stays
> in sync with the build, otherwise the Docker `npm ci` fails:
> `docker run --rm -v "$PWD/frontend:/app" -w /app node:22-alpine npm install --package-lock-only`

## Tests

```bash
cd backend && pytest
```

## Releases (maintainers)

Every commit pushed to `main` triggers `.github/workflows/release.yml`. It builds and publishes both
Docker images, then creates a tagged GitHub Release with generated notes. The release title shows the
version from `VERSION` (for example, `v0.5.1`), while its internal tag remains immutable, such as
`0.5.1-main.42.a1b2c3d4e5f6`, so host updates always select one exact build.

After both images succeed, the current `main` build is promoted to the rolling `:X.Y`, `:main`, and
`:latest` tags. The workflow then removes older Releases and GHCR versions while retaining the current
and immediately previous builds for automatic application rollback. If a newer commit reaches `main`
while an older build is running, the older build cannot promote or clean up the newer release.

The root **`VERSION`** file selects the release series. Bump it to a semantic version such as `1.0.0`
when starting a new series; ordinary commits should leave it unchanged.

> One-time org setup: the `spaceworks-backend` and `spaceworks-frontend` GHCR packages must be set to **Public**
> (org → Packages → each package → visibility) so anyone can `docker compose pull` without logging in.
