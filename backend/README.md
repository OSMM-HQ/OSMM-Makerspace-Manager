# Backend

Django REST API for OSMM.

## Run Locally

From the repo root, start Postgres:

```powershell
docker compose up -d db
```

Then run the backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

The backend runs at:

```text
http://localhost:8000/api
```

## Admin Panel

The Django admin panel is backend-only:

```text
Local: http://localhost:8000/admin/
Docker: http://localhost:8001/admin/
```

Create an admin user with:

```powershell
cd backend
python manage.py createsuperuser
```

In Docker:

```powershell
docker compose exec backend python manage.py createsuperuser
```

Use the admin panel to create makerspaces. Public makerspaces need:

```text
public_inventory_enabled=True
unique slug
```

The frontend public directory lists enabled makerspaces automatically through:

```text
GET /api/public/makerspaces/
```

## API Docs

Swagger UI and ReDoc are set up in the backend through `drf-spectacular`.

```text
ReDoc: http://localhost:8000/
Swagger UI: http://localhost:8000/docs/
OpenAPI schema: http://localhost:8000/schema/
```

When running through `docker compose`, the backend host port is `8001`:

```text
Backend API: http://localhost:8001/api
ReDoc: http://localhost:8001/
Swagger UI: http://localhost:8001/docs/
OpenAPI schema: http://localhost:8001/schema/
```

The routes are defined in `config/urls.py`:

```text
/
/admin/
/schema/
/docs/
```

## Run Tests

```powershell
cd backend
pytest
```
