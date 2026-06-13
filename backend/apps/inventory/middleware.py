import hashlib
import hmac
import logging
import time
from urllib.parse import urlsplit

from django.conf import settings
from django.http import JsonResponse

logger = logging.getLogger(__name__)


class FrontendHMACMiddleware:
    """Validate signed client requests for protected API paths using the ApiClient registry."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._should_validate(request) and not self._is_valid(request):
            return JsonResponse({"detail": "Invalid client signature."}, status=401)
        return self.get_response(request)

    def _should_validate(self, request):
        if request.method == "OPTIONS" or not settings.API_CLIENT_AUTH_REQUIRED:
            return False
        return any(
            request.path.startswith(p) for p in settings.HMAC_PROTECTED_PATH_PREFIXES
        )

    def _is_valid(self, request):
        if self._publishable_key_is_valid(request):
            return True
        if self._frontend_client_is_valid(request):
            return True
        try:
            from apps.apiclients.models import ApiClient

            client_id = request.headers.get("X-Client-Id", "")
            timestamp = request.headers.get("X-Timestamp", "")
            signature = request.headers.get("X-Signature", "")
            if not (client_id and timestamp and signature):
                return False

            client = ApiClient.objects.filter(
                client_id=client_id, is_active=True
            ).first()
            if client is None:
                return False

            if not self._origin_ok(request, client):
                return False
            if not self._client_scope_ok(request, client):
                return False
            if not self._request_scope_ok(request, client):
                return False

            try:
                skew = abs(int(time.time()) - int(timestamp))
            except ValueError:
                return False
            if skew > settings.HMAC_MAX_CLOCK_SKEW_SECONDS:
                return False

            message = b"\n".join([
                request.method.upper().encode(),
                request.get_full_path().encode(),
                timestamp.encode(),
                request.body,
            ])
            expected = hmac.new(
                client.get_secret().encode(), message, hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(signature, expected)
        except Exception:  # fail safe - never 500 the request flow
            logger.exception("ApiClient signature validation failed")
            return False

    def _publishable_key_is_valid(self, request):
        key = request.headers.get("X-Publishable-Key") or request.GET.get("key")
        if not key:
            return False
        try:
            from apps.makerspaces.models import Makerspace

            makerspace = Makerspace.objects.filter(
                public_api_key=key,
                public_inventory_enabled=True,
            ).first()
            if makerspace is None:
                return False
            if not self._makerspace_scope_ok(request, makerspace):
                return False
            return self._publishable_origin_ok(request, makerspace)
        except Exception:
            logger.exception("Publishable key validation failed")
            return False

    def _publishable_origin_ok(self, request, makerspace):
        origins = set(makerspace.cors_allowed_origins or [])
        if not origins:
            return False
        raw = request.headers.get("Origin") or request.headers.get("Referer", "")
        if not raw:
            return False
        parts = urlsplit(raw)
        candidate = f"{parts.scheme}://{parts.netloc}" if parts.scheme else ""
        return candidate in origins

    def _origin_ok(self, request, client):
        # Fail closed (review fix #4): a client with no configured origins is rejected,
        # so the exact-origin check can never be skipped by omission. The model + admin
        # also require at least one origin (ApiClient.clean).
        if not client.allowed_origins:
            return False
        raw = request.headers.get("Origin") or request.headers.get("Referer", "")
        if not raw:
            return False
        parts = urlsplit(raw)
        candidate = f"{parts.scheme}://{parts.netloc}" if parts.scheme else ""
        return candidate in set(client.allowed_origins)

    def _frontend_client_is_valid(self, request):
        try:
            from apps.apiclients.models import ApiClient

            client_id = request.headers.get("X-Client-Id", "")
            timestamp = request.headers.get("X-Timestamp", "")
            signature = request.headers.get("X-Signature", "")
            if not client_id or timestamp or signature:
                return False
            client = ApiClient.objects.select_related("makerspace").filter(
                client_id=client_id,
                is_active=True,
            ).first()
            if client is None:
                return False
            return (
                client.client_type == "browser"
                and self._origin_ok(request, client)
                and self._client_scope_ok(request, client)
                and self._request_scope_ok(request, client)
            )
        except Exception:
            logger.exception("Frontend ApiClient validation failed")
            return False

    def _client_scope_ok(self, request, client):
        if client.makerspace_id is None:
            return True
        target = self._path_makerspace(request)
        return target is None or target.pk == client.makerspace_id

    def _makerspace_scope_ok(self, request, makerspace):
        target = self._path_makerspace(request)
        return target is None or target.pk == makerspace.pk

    def _request_scope_ok(self, request, client):
        scopes = set(client.scopes or [])
        if not scopes:
            return True
        path = request.path
        method = request.method.upper()
        if "/public/" in path:
            required = "public:write" if method not in {"GET", "HEAD", "OPTIONS"} else "public:read"
            return required in scopes or "public:*" in scopes
        if "/admin/" in path:
            if "/reports/" in path or "/analytics/" in path:
                return "reports:read" in scopes or "admin:read" in scopes or "admin:*" in scopes
            required = "admin:write" if method not in {"GET", "HEAD", "OPTIONS"} else "admin:read"
            return required in scopes or "admin:*" in scopes
        return True

    def _path_makerspace(self, request):
        marker = "/public/"
        if marker not in request.path:
            return None
        tail = request.path.split(marker, 1)[1]
        identifier = tail.split("/", 1)[0]
        if not identifier or identifier == "makerspaces" or identifier == "requests":
            return None
        try:
            from apps.makerspaces.lookup import get_public_makerspace

            return get_public_makerspace(identifier)
        except Exception:
            return None
