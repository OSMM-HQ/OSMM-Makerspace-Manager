from urllib.parse import urlsplit

from corsheaders.signals import check_request_enabled

from apps.makerspaces.models import Makerspace
from apps.makerspaces.platform import makerspace_public_origins, makerspace_staff_origins

_STAFF_PATH_PREFIXES = (
    "/api/v1/auth/",
    "/api/v1/admin/",
    "/api/v1/guest-admin/",
    "/api/v1/printing/manage/",
    "/api/v1/printing/admin/",
    "/api/v1/procurement/",
    "/api/v1/integrations/telegram/test-alert",
)


def _origin_host(origin):
    return (urlsplit(origin).hostname or "").lower()


def origin_is_registered(origin):
    if not origin:
        return False
    # Indexed lookup: a branded-domain origin matches by host; an API-client/public origin
    # matches by exact membership in cors_allowed_origins (jsonb containment).
    host = _origin_host(origin)
    if host:
        for makerspace in Makerspace.objects.filter(
            frontend_domain__iexact=host,
            archived_at__isnull=True,
        ):
            if origin in makerspace_public_origins(makerspace):
                return True
    return Makerspace.objects.filter(
        archived_at__isnull=True,
        cors_allowed_origins__contains=[origin],
    ).exists()


def staff_origin_is_registered(origin):
    """Credentialed staff-auth endpoints only trust the configured frontend domain."""
    if not origin:
        return False
    host = _origin_host(origin)
    if not host:
        return False
    # Narrow to the (at most one) makerspace owning this host, then require the EXACT
    # https://<frontend_domain> origin — never cors_allowed_origins.
    for makerspace in Makerspace.objects.filter(
        frontend_domain__iexact=host,
        archived_at__isnull=True,
    ):
        if origin in makerspace_staff_origins(makerspace):
            return True
    return False


def _is_staff_path(path):
    if not path:
        return False
    for prefix in _STAFF_PATH_PREFIXES:
        if prefix == "/api/v1/integrations/telegram/test-alert":
            if path == prefix:
                return True
            continue
        if path == prefix or path.startswith(prefix):
            return True
    return False


def cors_allow_registered_frontend(sender, request, **kwargs):
    origin = request.headers.get("Origin")
    if _is_staff_path(request.path):
        return staff_origin_is_registered(origin)
    return origin_is_registered(origin)


def register_signal():
    check_request_enabled.connect(cors_allow_registered_frontend)
