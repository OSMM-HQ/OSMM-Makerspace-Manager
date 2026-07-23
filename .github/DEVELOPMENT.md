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

## Cutting a release (maintainers)

Releases are driven straight from `main` and publish Docker images plus a tagged GitHub Release:

1. Bump the root **`VERSION`** file to the new semantic version, e.g. `1.0.0`.
2. Commit and push to `main`.

Changing `VERSION` on `main` triggers `.github/workflows/release.yml`, which validates the version
and publishes `:X.Y.Z`, `:X.Y`, and `:latest` for both `spaceworks-backend` and `spaceworks-frontend`.
After the images succeed, it creates the `vX.Y.Z` tag and GitHub Release with generated release notes.
An ordinary push to `main` without a `VERSION` change does not publish a release.

> One-time org setup: the `spaceworks-backend` and `spaceworks-frontend` GHCR packages must be set to **Public**
> (org → Packages → each package → visibility) so anyone can `docker compose pull` without logging in.
