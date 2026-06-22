from urllib.parse import urlsplit

from apps.makerspaces.models import Makerspace
from apps.makerspaces.platform import makerspace_staff_origins


NO_STAFF_ORIGIN_SCOPE = object()
AMBIGUOUS_STAFF_ORIGIN_SCOPE = object()


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
    if "makerspace_id" in kwargs:
        return int(kwargs["makerspace_id"])
    match = getattr(request, "resolver_match", None)
    url_name = getattr(match, "url_name", "")
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
    "admin-inventory-detail": ("inventory.InventoryProduct", "makerspace_id"),
    "admin-inventory-image": ("inventory.InventoryProduct", "makerspace_id"),
    "admin-printer-image": ("printing.PrintPrinter", "makerspace_id"),
    "admin-inventory-adjust-quantity": ("inventory.InventoryProduct", "makerspace_id"),
    "admin-inventory-lending-history": ("inventory.InventoryProduct", "makerspace_id"),
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
    "stocktake-complete": ("operations.StocktakeSession", "makerspace_id"),
    "stocktake-approve": ("operations.StocktakeSession", "makerspace_id"),
    "stocktake-apply-adjustments": ("operations.StocktakeSession", "makerspace_id"),
    "qr-print-batch-detail": ("operations.QrPrintBatch", "makerspace_id"),
    "qr-print-batch-items": ("operations.QrPrintBatch", "makerspace_id"),
    "qr-print-batch-download": ("operations.QrPrintBatch", "makerspace_id"),
    "direct-loan-return": ("hardware_requests.PublicToolLoan", "makerspace_id"),
    "managed-printer-detail": ("printing.PrintPrinter", "makerspace_id"),
    "managed-spool-detail": ("printing.FilamentSpool", "makerspace_id"),
    "managed-file-url": ("printing.PrintRequestFile", "makerspace_id"),
    "to-buy-detail": ("procurement.ToBuyItem", "makerspace_id"),
    **{name: ("hardware_requests.HardwareRequest", "makerspace_id") for name in _REQUEST_ACTIONS},
    **{name: ("printing.PrintRequest", "makerspace_id") for name in _PRINT_ACTIONS},
}
