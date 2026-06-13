from urllib.parse import urlparse

from apps.makerspaces.models import Makerspace, TenantFrontend, default_branding_config, default_theme_config


MODULE_WORKFLOWS = {
    "public_inventory": ["catalog"],
    "request_workflow": ["request_submit", "request_status"],
    "self_checkout": ["self_checkout", "self_return"],
    "staff_admin": ["staff_inventory", "staff_requests"],
    "guest_handover": ["guest_issue", "guest_return"],
    "scanner": ["qr_scan", "container_lookup"],
    "qr_management": ["qr_generate", "qr_revoke", "qr_print"],
    "bulk_import": ["bulk_import"],
    "containers": ["container_lookup", "container_move"],
    "stock_transfers": ["stock_transfer"],
    "stocktake": ["stocktake"],
    "reports": ["analytics", "report_export"],
    "qr_print_batches": ["qr_print_batch"],
    "asset_units": ["asset_qr_generation"],
    "printing": ["printing_requests"],
    "telegram": ["telegram_alerts"],
    "maintenance": ["maintenance"],
    "procurement": ["procurement"],
    "evidence_uploads": ["evidence_uploads"],
}


def origin_to_hostname(origin):
    if not origin:
        return ""
    parsed = urlparse(origin if "://" in origin else f"//{origin}")
    return (parsed.hostname or "").lower()


def frontend_allowed_origins(frontend):
    origins = list(frontend.allowed_origins or [])
    if frontend.hostname:
        origins.extend([f"https://{frontend.hostname}", f"http://{frontend.hostname}"])
    return sorted(set(origins))


def resolve_frontend(*, tenant=None, slug=None, origin=None, host=None):
    queryset = TenantFrontend.objects.select_related("makerspace").filter(is_active=True)
    if tenant:
        frontend = queryset.filter(token=tenant).first()
        if frontend:
            return frontend
        makerspace = Makerspace.objects.filter(public_code__iexact=tenant).first()
        if makerspace:
            return primary_or_synthetic_frontend(makerspace)
    if slug:
        makerspace = Makerspace.objects.filter(slug=slug).first()
        if makerspace:
            return primary_or_synthetic_frontend(makerspace)
    hostname = origin_to_hostname(origin) or origin_to_hostname(host)
    if hostname:
        frontend = queryset.filter(hostname=hostname).first()
        if frontend:
            return frontend
        for candidate in queryset:
            if origin and origin in frontend_allowed_origins(candidate):
                return candidate
    return None


def primary_or_synthetic_frontend(makerspace):
    frontend = makerspace.frontends.filter(is_active=True, is_primary=True).first()
    if frontend:
        return frontend
    frontend = makerspace.frontends.filter(is_active=True).order_by("id").first()
    if frontend:
        return frontend
    return TenantFrontend(
        makerspace=makerspace,
        frontend_type=TenantFrontend.FrontendType.PUBLIC_PORTAL,
        allowed_origins=makerspace.cors_allowed_origins,
        enabled_modules=[],
        theme_config={},
        branding_config={},
        is_active=True,
    )


def modules_for_frontend(frontend):
    base = frontend.makerspace.enabled_modules or []
    overrides = frontend.enabled_modules or []
    return sorted(set(overrides or base))


def module_enabled(makerspace, module_key):
    return module_key in set(makerspace.enabled_modules or [])


def bootstrap_payload(frontend):
    makerspace = frontend.makerspace
    modules = modules_for_frontend(frontend)
    theme = default_theme_config()
    theme.update(makerspace.theme_config or {})
    theme.update(frontend.theme_config or {})
    branding = default_branding_config()
    branding.update(makerspace.branding_config or {})
    branding.update(frontend.branding_config or {})
    if not branding.get("display_name"):
        branding["display_name"] = makerspace.name
    workflows = sorted(
        {
            workflow
            for module in modules
            for workflow in MODULE_WORKFLOWS.get(module, [])
        }
    )
    return {
        "makerspace": {
            "id": makerspace.id,
            "name": makerspace.name,
            "slug": makerspace.slug,
            "public_code": makerspace.public_code,
            "location": makerspace.location,
        },
        "frontend": {
            "type": frontend.frontend_type,
            "hostname": frontend.hostname or "",
            "allowed_origins": frontend_allowed_origins(frontend),
        },
        "modules": modules,
        "workflows": workflows,
        "theme": theme,
        "branding": branding,
        "public_api": {
            "base_url": "/api/v1",
            "publishable_key": makerspace.public_api_key,
            "inventory_path": f"/api/v1/public/{makerspace.slug}/inventory/",
        },
    }
