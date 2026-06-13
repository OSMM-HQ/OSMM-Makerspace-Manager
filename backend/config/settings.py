from datetime import timedelta
from pathlib import Path

import environ
from corsheaders.defaults import default_headers

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")
from config.unfold import UNFOLD

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "storages",
    "apps.accounts",
    "apps.makerspaces",
    "apps.apiclients",
    "apps.boxes",
    "apps.inventory",
    "apps.hardware_requests",
    "apps.checkin",
    "apps.printing",
    "apps.audit",
    "apps.evidence",
    "apps.admin_api",
    "apps.integrations",
    "apps.operations",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "apps.inventory.middleware.FrontendHMACMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {"default": env.db()}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="evidence")
AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default="http://localhost:9000")
AWS_S3_PUBLIC_ENDPOINT_URL = env(
    "AWS_S3_PUBLIC_ENDPOINT_URL",
    default=AWS_S3_ENDPOINT_URL,
)
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="us-east-1")
AWS_S3_ADDRESSING_STYLE = "path"
AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_DEFAULT_ACL = None
AWS_QUERYSTRING_AUTH = True

STORAGES = {
    "default": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"},
    # Match prior behavior: plain static storage (whitenoise serves it via middleware).
    # Manifest storage would require collectstatic before runserver, breaking host dev.
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

EVIDENCE_URL_TTL_SECONDS = env.int("EVIDENCE_URL_TTL_SECONDS", default=300)
EVIDENCE_MAX_BYTES = env.int("EVIDENCE_MAX_BYTES", default=10485760)
EVIDENCE_ALLOWED_MIME = ["image/jpeg", "image/png", "image/webp"]

CHECKIN_MODE = env("CHECKIN_MODE", default="stub")
CHECKIN_API_URL = env("CHECKIN_API_URL", default="")
CHECKIN_API_KEY = env("CHECKIN_API_KEY", default="")
CHECKIN_TIMEOUT = env.float("CHECKIN_TIMEOUT", default=5.0)

TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", default="")
TELEGRAM_API_URL = env("TELEGRAM_API_URL", default="https://api.telegram.org")
# Secret passed to Telegram's setWebhook(secret_token=...); Telegram echoes it in
# the X-Telegram-Bot-Api-Secret-Token header on every callback. The webhook fails
# closed when this is unset, so an unconfigured webhook can't be driven by spoofed
# callbacks.
TELEGRAM_WEBHOOK_SECRET = env("TELEGRAM_WEBHOOK_SECRET", default="")

EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Makerspace <noreply@makerspace.local>")

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:5000", "http://localhost:5173"],
)
CORS_ALLOW_HEADERS = (
    *default_headers,
    "x-client-id",
    "x-signature",
    "x-timestamp",
    "x-refresh-csrf",
    "x-publishable-key",
)
CORS_ALLOW_CREDENTIALS = True

HMAC_CLIENT_ID = env("HMAC_CLIENT_ID", default="")
HMAC_SECRET = env("HMAC_SECRET", default="")
HMAC_MAX_CLOCK_SKEW_SECONDS = env.int("HMAC_MAX_CLOCK_SKEW_SECONDS", default=300)
HMAC_PROTECTED_PATH_PREFIXES = env.list(
    "HMAC_PROTECTED_PATH_PREFIXES",
    default=["/api/public/", "/api/v1/public/"],
)
# Fernet key for encrypting ApiClient secrets at rest. Generate with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# default="" (review fix #5) so settings import never fails when encryption isn't used;
# _fernet() raises ImproperlyConfigured only when a key is actually needed. Tests/CI get a
# real key from .env / docker-compose (added below).
API_CLIENT_ENC_KEY = env("API_CLIENT_ENC_KEY", default="")
# When True, requests to HMAC_PROTECTED_PATH_PREFIXES must carry a valid signed client.
API_CLIENT_AUTH_REQUIRED = env.bool("API_CLIENT_AUTH_REQUIRED", default=False)

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 24,
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    # DENY BY DEFAULT (review fix #4): every view requires auth unless it explicitly
    # opts into AllowAny. Public views are marked AllowAny in Step 3b.
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "EXCEPTION_HANDLER": "apps.hardware_requests.exceptions.workflow_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "checkin_verify": env("THROTTLE_CHECKIN_VERIFY", default="30/min"),
        "request_submit": env("THROTTLE_REQUEST_SUBMIT", default="10/min"),
        "request_status": env("THROTTLE_REQUEST_STATUS", default="60/min"),
        "public_read": env("THROTTLE_PUBLIC_READ", default="120/min"),
    },
    "URL_FORMAT_OVERRIDE": None,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# Cross-site refresh cookie (frontends live on separate origins).
AUTH_REFRESH_COOKIE = "refresh_token"
# CSRF defense for the cookie-bearing endpoints (refresh/logout): the view requires
# this custom header to be PRESENT — a non-simple header forces a CORS preflight that
# an attacker's origin cannot pass — AND validates the Origin header against the
# allowlist (review fixes #1, #8). The header VALUE is not a secret; presence + Origin
# is the defense. This works cross-origin where a readable double-submit cookie cannot.
AUTH_REFRESH_CSRF_HEADER = "X-Refresh-CSRF"
AUTH_COOKIE_PATH = "/api/v1/auth/"
# SameSite=None REQUIRES Secure or browsers silently drop the cookie (review fix #2).
# Prod (separate origins over HTTPS): SAMESITE=None, SECURE=True.
# Local dev: serve the frontend through a same-origin Vite proxy to the API and set
# AUTH_COOKIE_SAMESITE=Lax + AUTH_COOKIE_SECURE=False via .env (see Step 3c note).
AUTH_COOKIE_SAMESITE = env("AUTH_COOKIE_SAMESITE", default="None")
AUTH_COOKIE_SECURE = env.bool("AUTH_COOKIE_SECURE", default=True)

SPECTACULAR_SETTINGS = {
    "TITLE": "Makerspace Inventory Manager API",
    "DESCRIPTION": (
        "Multi-tenant makerspace hardware loan system.\n\n"
        "Public flow: browse inventory, search with `q`, page with `page`, "
        "verify Check-In, submit a borrow request, then track it by public token "
        "or verified Check-In identifier.\n\n"
        "Admin flow: authenticate with JWT, manage makerspaces, inventory, "
        "staff, QR labels, bulk imports, request review, issue, and return.\n\n"
        "Authentication: staff/admin endpoints use `Authorization: Bearer <access>`. "
        "Public browser endpoints can use `X-Publishable-Key` when public key "
        "hardening is enabled."
    ),
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVERS": [
        {"url": "http://localhost:8001", "description": "Local Docker backend"},
        {"url": "http://localhost:8000", "description": "Local Django runserver"},
    ],
    "TAGS": [
        {"name": "Auth", "description": "Staff login, refresh, logout, and profile."},
        {"name": "Public inventory", "description": "Public makerspace catalog browsing."},
        {"name": "Public requests", "description": "Public borrow request and status flows."},
        {"name": "Admin makerspaces", "description": "Admin makerspace CRUD."},
        {"name": "Admin inventory", "description": "Admin inventory CRUD and search lists."},
        {"name": "Admin requests", "description": "Review, handover, issue, and return workflows."},
        {"name": "Bulk import", "description": "Inventory import preview and apply workflow."},
        {"name": "Admin users", "description": "Staff, guest-admin, and access restriction."},
        {"name": "QR assets", "description": "QR-coded boxes, tools, scans, print, revoke."},
        {"name": "Telegram", "description": "Telegram webhook and alert integration."},
        {"name": "Printing", "description": "3D printing request and management APIs."},
        {"name": "Containers", "description": "Container hierarchy, movement, contents, and scan history."},
        {"name": "Stock transfers", "description": "Administrative stock movement between containers and makerspaces."},
        {"name": "Stocktake", "description": "Stocktake sessions, line counts, approvals, and adjustments."},
        {"name": "Analytics", "description": "Operational inventory analytics and report summaries."},
        {"name": "Reports", "description": "CSV and XLSX operational report exports."},
        {"name": "QR print batches", "description": "QR label batch creation, item management, and print HTML."},
        {"name": "Asset units", "description": "Individual asset unit generation and QR assignment."},
        {"name": "Health", "description": "Health and readiness probes."},
    ],
}
