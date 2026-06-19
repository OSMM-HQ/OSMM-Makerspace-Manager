from urllib.parse import urlparse

from apps.integrations.email import email_enabled
from apps.makerspaces.models import Makerspace, default_branding_config, default_theme_config


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


def makerspace_staff_origins(makerspace):
    if not makerspace.frontend_domain:
        return set()
    return {f"https://{makerspace.frontend_domain}"}


def makerspace_public_origins(makerspace):
    return makerspace_staff_origins(makerspace) | set(makerspace.cors_allowed_origins or [])


def resolve_frontend(*, tenant=None, slug=None, origin=None, host=None):
    if tenant:
        return Makerspace.objects.filter(
            public_code__iexact=tenant,
            archived_at__isnull=True,
        ).first()
    if slug:
        return Makerspace.objects.filter(
            slug=slug,
            archived_at__isnull=True,
        ).first()
    hostname = origin_to_hostname(origin) or origin_to_hostname(host)
    if hostname:
        return Makerspace.objects.filter(
            frontend_domain__iexact=hostname,
            archived_at__isnull=True,
        ).first()
    return None


def module_enabled(makerspace, module_key):
    return module_key in set(makerspace.enabled_modules or [])


def bootstrap_payload(makerspace):
    modules = sorted(set(makerspace.enabled_modules or []))
    theme = default_theme_config()
    theme.update(makerspace.theme_config or {})
    branding = default_branding_config()
    branding.update(makerspace.branding_config or {})
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
            "type": "makerspace",
            "hostname": makerspace.frontend_domain or "",
            "allowed_origins": sorted(makerspace_public_origins(makerspace)),
        },
        "modules": modules,
        "workflows": workflows,
        "theme": theme,
        "branding": branding,
        "email_enabled": email_enabled(),
        "public_api": {
            "base_url": "/api/v1",
            "publishable_key": makerspace.public_api_key,
            "inventory_path": f"/api/v1/public/{makerspace.slug}/inventory/",
        },
    }
