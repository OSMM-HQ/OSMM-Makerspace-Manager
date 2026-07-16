from urllib.parse import urlsplit

from django.conf import settings

from apps.makerspaces.models import Makerspace
from apps.makerspaces.platform import makerspace_staff_origins


NO_STAFF_ORIGIN_SCOPE = object()
AMBIGUOUS_STAFF_ORIGIN_SCOPE = object()
_MAKERSPACE_KWARG_ROUTES = {
    'admin-maintenance-schedule-list-create': 'makerspace_id',
    'admin-maintenance-log-list-create': 'makerspace_id',
    'admin-bookable-space-list-create': 'makerspace_id',
    'admin-event-list-create': 'makerspace_id',
    "admin-machine-types": "makerspace_id",
    "admin-machine-type-detail": "makerspace_id",
    "admin-makerspace-provision-subdomain": "makerspace_id",
    "admin-makerspace-subdomain-request": "makerspace_id",
}


def _origin_candidate(request):
    raw = request.headers.get("Origin") or request.headers.get("Referer", "")
    if not raw:
        return ""
    parts = urlsplit(raw)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""


def staff_origin_scope(request):
    origin = _origin_candidate(request)
    if not origin:
        return NO_STAFF_ORIGIN_SCOPE
    if origin in set(settings.PLATFORM_STAFF_ORIGINS):
        return NO_STAFF_ORIGIN_SCOPE

    matches = {
        makerspace.id
        for makerspace in Makerspace.objects.filter(
            frontend_domain__isnull=False,
            archived_at__isnull=True,
        )
        if origin in makerspace_staff_origins(makerspace)
    }
    if not matches:
        return NO_STAFF_ORIGIN_SCOPE
    if len(matches) > 1:
        return AMBIGUOUS_STAFF_ORIGIN_SCOPE
    return next(iter(matches))


def origin_scoped_makerspace_id(request):
    scope = staff_origin_scope(request)
    if scope in (NO_STAFF_ORIGIN_SCOPE, AMBIGUOUS_STAFF_ORIGIN_SCOPE):
        return None
    return scope


def staff_origin_scope_allows(request, view=None):
    scope = staff_origin_scope(request)
    if scope is NO_STAFF_ORIGIN_SCOPE:
        return True
    if scope is AMBIGUOUS_STAFF_ORIGIN_SCOPE:
        return False

    target = _target_makerspace_id(request, view)
    if target is None:
        return _global_endpoint_allowed(request)
    return target == scope


def object_in_staff_origin_scope(request, obj):
    scope = staff_origin_scope(request)
    if scope is NO_STAFF_ORIGIN_SCOPE:
        return True
    if scope is AMBIGUOUS_STAFF_ORIGIN_SCOPE:
        return False
    target = _object_makerspace_id(obj)
    return target is None or target == scope


def _global_endpoint_allowed(request):
    match = getattr(request, "resolver_match", None)
    return getattr(match, "url_name", "") == "admin-makerspaces"


def _target_makerspace_id(request, view=None):
    kwargs = getattr(view, "kwargs", {}) if view is not None else {}
    match = getattr(request, 'resolver_match', None)
    url_name = getattr(match, 'url_name', '')
    registered_kwarg = _MAKERSPACE_KWARG_ROUTES.get(url_name)
    if registered_kwarg in kwargs:
        return int(kwargs[registered_kwarg])
    if "makerspace_id" in kwargs:
        return int(kwargs["makerspace_id"])
    if url_name == "admin-makerspace" and "pk" in kwargs:
        return int(kwargs["pk"])
    query_value = getattr(request, "query_params", {}).get("makerspace")
    if query_value not in (None, ""):
        try:
            return int(query_value)
        except (TypeError, ValueError):
            return None
    pk = kwargs.get("pk")
    if pk is None:
        return None
    return _lookup_makerspace_id(url_name, pk)


def _lookup_makerspace_id(url_name, pk):
    lookup = _MODEL_LOOKUPS.get(url_name)
    if lookup is None:
        return None
    model_path, field = lookup
    model = _model_for_path(model_path)
    try:
        return model.objects.values_list(field, flat=True).get(pk=pk)
    except model.DoesNotExist:
        return None


def _object_makerspace_id(obj):
    makerspace_id = getattr(obj, "makerspace_id", None)
    if makerspace_id is not None:
        return makerspace_id
    bucket = getattr(obj, "bucket", None)
    if bucket is not None:
        return getattr(bucket, "makerspace_id", None)
    print_request = getattr(obj, "print_request", None)
    if print_request is not None:
        return getattr(print_request, "makerspace_id", None)
    return None


def _model_for_path(model_path):
    app_label, model_name = model_path.split(".")
    if app_label == "makerspaces":
        from apps.makerspaces import models
    elif app_label == "inventory":
        from apps.inventory import models
    elif app_label == "boxes":
        from apps.boxes import models
    elif app_label == "evidence":
        from apps.evidence import models
    elif app_label == "operations":
        from apps.operations import models
    elif app_label == "hardware_requests":
        from apps.hardware_requests import models
    elif app_label == "printing":
        from apps.printing import models
    elif app_label == "procurement":
        from apps.procurement import models
    elif app_label == "warranty":
        from apps.warranty import models
    elif app_label == "machines":
        from apps.machines import models
    elif app_label == 'events':
        from apps.events import models
    elif app_label == 'bookings':
        from apps.bookings import models
    elif app_label == "maintenance":
        from apps.maintenance import models
    elif app_label == "makerspaces":
        from apps.makerspaces import models
    else:
        raise LookupError(model_path)
    return getattr(models, model_name)


_REQUEST_ACTIONS = {
    "request-accept",
    "request-reject",
    "request-assign-box",
    "request-issue",
    "request-return-due",
    "request-return",
    "guest-admin-request-return",
    "request-timeline",
}
_PRINT_ACTIONS = {
    "managed-request-detail",
    "managed-request-accept",
    "managed-request-reject",
    "managed-request-start",
    "managed-request-complete",
    "managed-request-collect",
    "managed-request-fail",
    "managed-request-reprint",
}
_MODEL_LOOKUPS = {
    "admin-membership-revoke": (
        "makerspaces.MakerspaceMembership",
        "makerspace_id",
    ),
    "admin-maintenance-schedule-detail": (
        "maintenance.MaintenanceSchedule",
        "machine__makerspace_id",
    ),
    "admin-maintenance-schedule-deactivate": (
        "maintenance.MaintenanceSchedule",
        "machine__makerspace_id",
    ),
    "admin-maintenance-log-document-presign": (
        "maintenance.MaintenanceLog",
        "machine__makerspace_id",
    ),
    "admin-maintenance-log-document-finalize": (
        "maintenance.MaintenanceLog",
        "machine__makerspace_id",
    ),
    "admin-maintenance-log-document-url": (
        "maintenance.MaintenanceLogDocument",
        "log__machine__makerspace_id",
    ),
    "admin-maintenance-log-document-detail": (
        "maintenance.MaintenanceLogDocument",
        "log__machine__makerspace_id",
    ),
    'admin-bookable-space-detail': ('bookings.BookableSpace', 'makerspace_id'),
    'admin-bookable-space-deactivate': (
        'bookings.BookableSpace',
        'makerspace_id',
    ),
    'admin-bookable-space-image-presign': (
        'bookings.BookableSpace',
        'makerspace_id',
    ),
    'admin-bookable-space-image-finalize': (
        'bookings.BookableSpace',
        'makerspace_id',
    ),
    'admin-bookable-space-image-delete': (
        'bookings.BookableSpace',
        'makerspace_id',
    ),
    'admin-space-booking-list': ('bookings.BookableSpace', 'makerspace_id'),
    'admin-booking-cancel': ('bookings.Booking', 'space__makerspace_id'),
    'admin-booking-complete': ('bookings.Booking', 'space__makerspace_id'),
    'admin-booking-no-show': ('bookings.Booking', 'space__makerspace_id'),
    'admin-event-detail': ('events.Event', 'makerspace_id'),
    'admin-event-publish': ('events.Event', 'makerspace_id'),
    'admin-event-cancel': ('events.Event', 'makerspace_id'),
    'admin-event-complete': ('events.Event', 'makerspace_id'),
    'admin-event-registration-list': ('events.Event', 'makerspace_id'),
    'admin-event-registration-mark-attended': (
        'events.EventRegistration',
        'event__makerspace_id',
    ),
    'admin-machine-operator-candidates': ('machines.Machine', 'makerspace_id'),
    'admin-machine-publicity': ('machines.Machine', 'makerspace_id'),
    "makerspace-verify-domain": ("makerspaces.Makerspace", "id"),
    "admin-inventory-detail": ("inventory.InventoryProduct", "makerspace_id"),
    "admin-inventory-image": ("inventory.InventoryProduct", "makerspace_id"),
    "admin-printer-image": ("printing.PrintPrinter", "makerspace_id"),
    "admin-inventory-asset-detail": ("inventory.InventoryAsset", "makerspace_id"),
    "admin-asset-warranty": ("inventory.InventoryAsset", "makerspace_id"),
    "admin-printer-warranty": ("printing.PrintPrinter", "makerspace_id"),
    "admin-machine-warranty": ("machines.Machine", "makerspace_id"),
    "admin-warranty-document-presign": ("warranty.Warranty", "makerspace_id"),
    "admin-warranty-documents": ("warranty.Warranty", "makerspace_id"),
    "admin-warranty-document-url": ("warranty.WarrantyDocument", "warranty__makerspace_id"),
    "admin-warranty-document-detail": ("warranty.WarrantyDocument", "warranty__makerspace_id"),
    "admin-inventory-adjust-quantity": ("inventory.InventoryProduct", "makerspace_id"),
    "admin-inventory-lending-history": ("inventory.InventoryProduct", "makerspace_id"),
    "admin-inventory-chain-of-custody": ("inventory.InventoryProduct", "makerspace_id"),
    "admin-needs-fix-action": ("inventory.InventoryProduct", "makerspace_id"),
    "admin-category-detail": ("inventory.Category", "makerspace_id"),
    "container-detail": ("boxes.Box", "makerspace_id"),
    "container-move": ("boxes.Box", "makerspace_id"),
    "container-contents": ("boxes.Box", "makerspace_id"),
    "container-history": ("boxes.Box", "makerspace_id"),
    "qr-print": ("boxes.QrCode", "makerspace_id"),
    "qr-revoke": ("boxes.QrCode", "makerspace_id"),
    "qr-rebind-target": ("boxes.QrCode", "makerspace_id"),
    "evidence-detail": ("evidence.EvidencePhoto", "makerspace_id"),
    "stock-transfer-detail": ("operations.StockTransfer", "makerspace_id"),
    "stocktake-detail": ("operations.StocktakeSession", "makerspace_id"),
    "stocktake-count-lines": ("operations.StocktakeSession", "makerspace_id"),
    "stocktake-resolve-scan": ("operations.StocktakeSession", "makerspace_id"),
    "stocktake-complete": ("operations.StocktakeSession", "makerspace_id"),
    "stocktake-approve": ("operations.StocktakeSession", "makerspace_id"),
    "stocktake-apply-adjustments": ("operations.StocktakeSession", "makerspace_id"),
    "qr-print-batch-detail": ("operations.QrPrintBatch", "makerspace_id"),
    "qr-print-batch-items": ("operations.QrPrintBatch", "makerspace_id"),
    "qr-print-batch-download": ("operations.QrPrintBatch", "makerspace_id"),
    "direct-loan-return": ("hardware_requests.PublicToolLoan", "makerspace_id"),
    "problem-report-triage": ("hardware_requests.PublicProblemReport", "makerspace_id"),
    "managed-printer-detail": ("printing.PrintPrinter", "makerspace_id"),
    "managed-spool-detail": ("printing.FilamentSpool", "makerspace_id"),
    "managed-spool-adjustment": ("printing.FilamentSpool", "makerspace_id"),
    "managed-file-url": ("printing.PrintRequestFile", "makerspace_id"),
    "to-buy-detail": ("procurement.ToBuyItem", "makerspace_id"),
    "to-buy-move-to-inventory": ("procurement.ToBuyItem", "makerspace_id"),
    "to-buy-move-to-printing": ("procurement.ToBuyItem", "makerspace_id"),
    "to-buy-receipt-presign": ("procurement.ToBuyItem", "makerspace_id"),
    "to-buy-receipt-list": ("procurement.ToBuyItem", "makerspace_id"),
    "to-buy-receipt-url": ("procurement.ToBuyReceipt", "to_buy_item__makerspace_id"),
    "to-buy-receipt-detail": ("procurement.ToBuyReceipt", "to_buy_item__makerspace_id"),
    "admin-machine-detail": ("machines.Machine", "makerspace_id"),
    "admin-machine-image": ("machines.Machine", "makerspace_id"),
    "admin-machine-set-status": ("machines.Machine", "makerspace_id"),
    "admin-machine-retire": ("machines.Machine", "makerspace_id"),
    "admin-machine-unretire": ("machines.Machine", "makerspace_id"),
    "admin-machine-usage": ("machines.Machine", "makerspace_id"),
    "admin-machine-consumables": ("machines.Machine", "makerspace_id"),
    "admin-machine-consumable-detail": ("machines.Machine", "makerspace_id"),
    "admin-machine-consumption-log": ("machines.Machine", "makerspace_id"),
    "admin-machine-consumable-candidates": ("machines.Machine", "makerspace_id"),
    "admin-machine-operators": ("machines.Machine", "makerspace_id"),
    "admin-machine-operator-detail": ("machines.Machine", "makerspace_id"),
    "admin-machine-document-presign": ("machines.Machine", "makerspace_id"),
    "admin-machine-documents": ("machines.Machine", "makerspace_id"),
    "admin-machine-error-logs": ("machines.Machine", "makerspace_id"),
    "admin-machine-document-url": ("machines.MachineDocument", "machine__makerspace_id"),
    "admin-machine-document-detail": ("machines.MachineDocument", "machine__makerspace_id"),
    **{name: ("hardware_requests.HardwareRequest", "makerspace_id") for name in _REQUEST_ACTIONS},
    **{name: ("printing.PrintRequest", "makerspace_id") for name in _PRINT_ACTIONS},
}




