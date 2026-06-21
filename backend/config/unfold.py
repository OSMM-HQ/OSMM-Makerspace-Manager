import os

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

SITE_NAME = os.environ.get("ADMIN_SITE_NAME", "OSMM")


def _is_active_superuser(request):
    user = getattr(request, "user", None)
    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and user.is_superuser
        and getattr(user, "access_status", None)
        == getattr(getattr(user, "AccessStatus", None), "ACTIVE", "active")
    )


def _item(title, icon, route):
    # Every admin model is superadmin-only (U-SEC), so a single permission gate
    # applies to the whole sidebar.
    return {
        "title": _(title),
        "icon": icon,
        "link": reverse_lazy(route),
        "permission": _is_active_superuser,
    }


UNFOLD = {
    "SITE_TITLE": SITE_NAME,
    "SITE_HEADER": SITE_NAME,
    "SITE_SYMBOL": "inventory_2",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "THEME": "dark",
    "COLORS": {
        "primary": {
            "50": "245 243 255",
            "100": "237 233 254",
            "200": "221 214 254",
            "300": "196 181 253",
            "400": "167 139 250",
            "500": "139 92 246",
            "600": "124 58 237",
            "700": "109 40 217",
            "800": "91 33 182",
            "900": "76 29 149",
            "950": "46 16 101",
        }
    },
    "SIDEBAR": {
        "show_search": True,
        "navigation": [
            {
                "title": _("Inventory"),
                "separator": True,
                "items": [
                    _item("Makerspaces", "store", "admin:makerspaces_makerspace_changelist"),
                    _item("Inventory", "inventory_2", "admin:inventory_inventoryproduct_changelist"),
                    _item("Categories", "category", "admin:inventory_category_changelist"),
                    _item("Asset units", "qr_code_2", "admin:inventory_inventoryasset_changelist"),
                    _item("Containers", "package_2", "admin:boxes_box_changelist"),
                    _item("Inventory adjustments", "tune", "admin:operations_inventoryadjustment_changelist"),
                ],
            },
            {
                "title": _("Requests & loans"),
                "separator": True,
                "items": [
                    _item("Hardware requests", "assignment", "admin:hardware_requests_hardwarerequest_changelist"),
                    _item("Tool loans", "outbound", "admin:hardware_requests_publictoolloan_changelist"),
                    _item("Return events", "assignment_return", "admin:hardware_requests_returnevent_changelist"),
                    _item("Accountability", "gavel", "admin:hardware_requests_requesteraccountability_changelist"),
                    _item("Issued asset links", "link", "admin:hardware_requests_hardwarerequestitemasset_changelist"),
                ],
            },
            {
                "title": _("Operations"),
                "separator": True,
                "items": [
                    _item("Stock transfers", "swap_horiz", "admin:operations_stocktransfer_changelist"),
                    _item("Stocktakes", "fact_check", "admin:operations_stocktakesession_changelist"),
                    _item("QR print batches", "print", "admin:operations_qrprintbatch_changelist"),
                    _item("QR codes", "qr_code", "admin:boxes_qrcode_changelist"),
                    _item("QR scans", "barcode_reader", "admin:boxes_qrscanevent_changelist"),
                    _item("Box scans", "qr_code_scanner", "admin:boxes_boxscan_changelist"),
                ],
            },
            {
                "title": _("Procurement"),
                "separator": True,
                "items": [
                    _item("To-buy list", "shopping_cart", "admin:procurement_tobuyitem_changelist"),
                ],
            },
            {
                "title": _("3D printing"),
                "separator": True,
                "items": [
                    _item("Print buckets", "folder", "admin:printing_printbucket_changelist"),
                    _item("Print requests", "deployed_code", "admin:printing_printrequest_changelist"),
                    _item("Printers", "precision_manufacturing", "admin:printing_printprinter_changelist"),
                    _item("Filament spools", "fiber_smart_record", "admin:printing_filamentspool_changelist"),
                ],
            },
            {
                "title": _("Accounts & access"),
                "separator": True,
                "items": [
                    _item("Users", "person", "admin:accounts_user_changelist"),
                    _item("Staff memberships", "badge", "admin:makerspaces_makerspacemembership_changelist"),
                    _item("Groups", "groups", "admin:auth_group_changelist"),
                ],
            },
            {
                "title": _("Integrations"),
                "separator": True,
                "items": [
                    _item("API clients", "vpn_key", "admin:apiclients_apiclient_changelist"),
                    _item("API key requests", "approval", "admin:apiclients_apikeyrequest_changelist"),
                    _item("Platform email", "mail", "admin:integrations_platformemailsettings_changelist"),
                    _item("Email templates", "mail", "admin:integrations_emailtemplate_changelist"),
                    _item("Email logs", "mark_email_read", "admin:integrations_emaillog_changelist"),
                ],
            },
            {
                "title": _("Audit & evidence"),
                "separator": True,
                "items": [
                    _item("Audit log", "history", "admin:audit_auditlog_changelist"),
                    _item("Evidence photos", "photo_library", "admin:evidence_evidencephoto_changelist"),
                ],
            },
        ],
    },
}
