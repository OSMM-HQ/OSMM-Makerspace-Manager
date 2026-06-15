from corsheaders.signals import check_request_enabled

from apps.makerspaces.models import Makerspace, TenantFrontend


def origin_is_registered(origin):
    if not origin:
        return False
    from apps.makerspaces.platform import frontend_allowed_origins

    # Honor hostname-derived origins too (frontend_allowed_origins), so a frontend registered
    # only by hostname still passes CORS — matching bootstrap/resolve_frontend and keeping the
    # CORS allowlist in sync with the refresh/logout CSRF check (staff_origin_is_registered).
    for frontend in TenantFrontend.objects.filter(is_active=True):
        if origin in frontend_allowed_origins(frontend):
            return True
    for origins in Makerspace.objects.values_list("cors_allowed_origins", flat=True):
        if origin in (origins or []):
            return True
    return False


def staff_origin_is_registered(origin):
    """Stricter allowlist for credentialed staff-auth endpoints (refresh/logout CSRF).

    Only origins of an active STAFF-console TenantFrontend qualify — never public/portal
    frontends and never `Makerspace.cors_allowed_origins` (which holds public/3rd-party API
    client origins). This prevents a page on a public/integration origin from passing the
    refresh CSRF check and reading a staff access token."""
    if not origin:
        return False
    from apps.makerspaces.platform import frontend_allowed_origins

    staff_types = [
        TenantFrontend.FrontendType.STAFF_ADMIN,
        TenantFrontend.FrontendType.GUEST_HANDOVER,
        TenantFrontend.FrontendType.SUPERADMIN_CONSOLE,
    ]
    # Cover both explicit allowed_origins AND hostname-derived origins (frontend_allowed_origins),
    # so a staff frontend registered only by hostname still passes the refresh/logout CSRF check.
    for frontend in TenantFrontend.objects.filter(
        is_active=True, frontend_type__in=staff_types
    ):
        if origin in frontend_allowed_origins(frontend):
            return True
    return False


def cors_allow_registered_frontend(sender, request, **kwargs):
    origin = request.headers.get("Origin")
    return origin_is_registered(origin)


def register_signal():
    check_request_enabled.connect(cors_allow_registered_frontend)
