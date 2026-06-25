from django.db.models import Count, Max, Sum

from apps.accounts import rbac
from apps.boxes.models import QrScanEvent
from apps.hardware_requests.display import label_from_candidates, requester_label
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem
from apps.inventory.models import InventoryAsset, InventoryProduct


DEFAULT_REPORT_LIMIT = 100
MAX_REPORT_LIMIT = 500


REPORT_KEYS = [
    "summary",
    "taken-items",
    "active-loans",
    "returns",
    "damaged-missing",
    "damaged-lost",
    "qr-scans",
    "most-lent",
    "top-borrowers",
    "recently-added",
]


def report_data(report_key="summary", makerspace_id=None, *, limit=None, date_range=None):
    if report_key == "summary":
        return _summary(makerspace_id)
    return {"rows": report_rows(report_key, makerspace_id, limit=_normalized_limit(limit), date_range=date_range)}



def _normalized_limit(limit):
    if limit is None:
        limit = DEFAULT_REPORT_LIMIT
    return max(0, min(int(limit), MAX_REPORT_LIMIT))


def _limit_queryset(qs, limit):
    return qs if limit is None else qs[:limit]


def report_rows(report_key, makerspace_id=None, *, limit=None, date_range=None):
    aggregate = makerspace_id is None
    if report_key == "taken-items":
        return _taken_items(makerspace_id, aggregate, limit, date_range)
    if report_key == "active-loans":
        return _active_loans(makerspace_id, aggregate, limit, date_range)
    if report_key == "returns":
        return _returns(makerspace_id, aggregate, limit, date_range)
    if report_key == "damaged-missing":
        return _damaged_missing(makerspace_id, aggregate, limit)
    if report_key == "damaged-lost":
        return _damaged_lost(makerspace_id, aggregate, limit)
    if report_key == "qr-scans":
        return _qr_scans(makerspace_id, aggregate, limit, date_range)
    if report_key == "most-lent":
        return _most_lent(makerspace_id, aggregate, limit, date_range)
    if report_key == "top-borrowers":
        return _top_borrowers(makerspace_id, aggregate, limit, date_range)
    if report_key == "recently-added":
        return _recently_added(makerspace_id, aggregate, limit, date_range)
    data = report_data("summary", makerspace_id)
    return [["metric", "value"], *[[key, value] for key, value in data.items()]]


def _summary(makerspace_id):
    products = _products(makerspace_id)
    assets = _assets(makerspace_id)
    requests = _requests(makerspace_id)
    return {
        "products": products.count(),
        "assets": assets.count(),
        "active_loans": requests.filter(
            status__in=[
                HardwareRequest.Status.ISSUED,
                HardwareRequest.Status.PARTIALLY_RETURNED,
            ]
        ).count(),
        "available_quantity": products.aggregate(total=Sum("available_quantity"))["total"] or 0,
        "issued_quantity": products.aggregate(total=Sum("issued_quantity"))["total"] or 0,
        "damaged_quantity": products.aggregate(total=Sum("damaged_quantity"))["total"] or 0,
        "missing_quantity": products.aggregate(total=Sum("lost_quantity"))["total"] or 0,
    }


def _taken_items(makerspace_id, aggregate, limit=None, date_range=None):
    # Group by product_id (not name) so two distinct products sharing a name are not
    # merged — there is no unique (makerspace, name) constraint. Name stays the display column.
    group = ["product_id", "product__name"]
    display = ["product__name"]
    header = ["product", "issued_quantity"]
    if aggregate:
        group = ["request__makerspace_id", *group]
        display = ["request__makerspace_id", *display]
        header = ["makerspace_id", *header]
    qs = _apply_date_range(_items(makerspace_id), "request__issued_at", date_range).values(*group).annotate(quantity=Sum("issued_quantity")).order_by("-quantity")
    qs = _limit_queryset(qs, limit)
    return [header, *[[_value(row, key) for key in display] + [row["quantity"] or 0] for row in qs]]


def _active_loans(makerspace_id, aggregate, limit=None, date_range=None):
    header = ["id", "requester", "status", "issued_at"]
    if aggregate:
        header = ["makerspace_id", *header]
    qs = _apply_date_range(_requests(makerspace_id), "issued_at", date_range).select_related("requester").filter(
        status__in=[HardwareRequest.Status.ISSUED, HardwareRequest.Status.PARTIALLY_RETURNED]
    ).order_by("-issued_at")
    qs = _limit_queryset(qs, limit)
    return [header, *[_request_row(request, aggregate, request.issued_at) for request in qs]]


def _returns(makerspace_id, aggregate, limit=None, date_range=None):
    header = ["id", "requester", "status", "closed_at"]
    if aggregate:
        header = ["makerspace_id", *header]
    qs = _apply_date_range(_requests(makerspace_id), "closed_at", date_range).select_related("requester").filter(
        status__in=[HardwareRequest.Status.RETURNED, HardwareRequest.Status.CLOSED_WITH_ISSUE]
    ).order_by("-closed_at")
    qs = _limit_queryset(qs, limit)
    return [header, *[_request_row(request, aggregate, request.closed_at) for request in qs]]


def _request_row(request, aggregate, timestamp):
    # Readable holder label (never the internal checkin_<hash>); matches the ledger.
    prefix = [request.makerspace_id] if aggregate else []
    return [*prefix, request.id, requester_label(request), request.status, timestamp]


def _damaged_missing(makerspace_id, aggregate, limit=None):
    values = ["name", "damaged_quantity", "lost_quantity"]
    header = ["product", "damaged_quantity", "missing_quantity"]
    return _product_quantity_rows(makerspace_id, aggregate, values, header, limit)


def _damaged_lost(makerspace_id, aggregate, limit=None):
    values = ["name", "damaged_quantity", "lost_quantity"]
    header = ["product_name", "damaged_quantity", "lost_quantity"]
    return _product_quantity_rows(makerspace_id, aggregate, values, header, limit)


def _qr_scans(makerspace_id, aggregate, limit=None, date_range=None):
    values = ["context"]
    header = ["context", "count"]
    if aggregate:
        values = ["makerspace_id", *values]
        header = ["makerspace_id", *header]
    qs = _apply_date_range(_qr_events(makerspace_id), "created_at", date_range).values(*values).annotate(count=Count("id")).order_by(*values)
    qs = _limit_queryset(qs, limit)
    return [header, *[[_value(row, key) for key in values] + [row["count"]] for row in qs]]


def _most_lent(makerspace_id, aggregate, limit=None, date_range=None):
    # Group by product_id (not name) so distinct products sharing a name keep separate
    # lend counts; name remains the display column.
    group = ["product_id", "product__name"]
    display = ["product__name"]
    header = ["product_name", "times_lent", "total_quantity_lent"]
    if aggregate:
        group = ["request__makerspace_id", *group]
        display = ["request__makerspace_id", *display]
        header = ["makerspace_id", *header]
    qs = (
        _apply_date_range(_items(makerspace_id), "request__issued_at", date_range)
        .filter(issued_quantity__gt=0)
        .values(*group)
        .annotate(
            times_lent=Count("request_id", distinct=True),
            total_quantity_lent=Sum("issued_quantity"),
        )
        .order_by("-times_lent", "-total_quantity_lent", "product__name")
    )
    qs = _limit_queryset(qs, limit)
    return [
        header,
        *[
            [_value(row, key) for key in display]
            + [row["times_lent"], row["total_quantity_lent"] or 0]
            for row in qs
        ],
    ]


def _top_borrowers(makerspace_id, aggregate, limit=None, date_range=None):
    # Group by stable requester id only; request-level display fields can vary over
    # time and must not fragment a single borrower's totals.
    values = ["request__requester_id"]
    header = ["holder", "requests", "items_borrowed"]
    if aggregate:
        values = ["request__makerspace_id", *values]
        header = ["makerspace_id", *header]
    qs = (
        _apply_date_range(_items(makerspace_id), "request__issued_at", date_range)
        .filter(issued_quantity__gt=0)
        .values(*values)
        .annotate(
            requests=Count("request_id", distinct=True),
            items_borrowed=Sum("issued_quantity"),
            requester_username=Max("request__requester_username"),
            username=Max("request__requester__username"),
            external_id=Max("request__requester__external_checkin_user_id"),
        )
        .order_by(
            *(["request__makerspace_id"] if aggregate else []),
            "-requests",
            "-items_borrowed",
            "username",
        )
    )
    rows = []
    for row in qs:
        holder = label_from_candidates(
            row["requester_username"],
            row["external_id"],
            row["username"],
        )
        prefix = [row["request__makerspace_id"]] if aggregate else []
        rows.append([*prefix, holder, row["requests"], row["items_borrowed"] or 0])
    return [header, *rows]


def _recently_added(makerspace_id, aggregate, limit=None, date_range=None):
    values = ["name", "created_at", "total_quantity"]
    header = ["product_name", "created_at", "total_quantity"]
    if aggregate:
        values = ["makerspace_id", *values]
        header = ["makerspace_id", *header]
    qs = _apply_date_range(_products(makerspace_id), "created_at", date_range).order_by("-created_at", "-id")
    qs = _limit_queryset(qs, limit)
    return [header, *[[_value(product, key) for key in values] for product in qs]]


def _product_quantity_rows(makerspace_id, aggregate, values, header, limit=None):
    if aggregate:
        values = ["makerspace_id", *values]
        header = ["makerspace_id", *header]
    qs = _products(makerspace_id).order_by("name")
    qs = _limit_queryset(qs, limit)
    return [header, *[[_value(product, key) for key in values] for product in qs]]


def _products(makerspace_id):
    qs = InventoryProduct.objects.filter(is_archived=False)
    if makerspace_id is None:
        excluded = (
            rbac.superadmin_hidden_makerspace_ids()
            | rbac.archived_makerspace_ids()
        )
        return qs.exclude(makerspace_id__in=excluded) if excluded else qs
    return qs.filter(makerspace_id=makerspace_id)


def _assets(makerspace_id):
    # Exclude assets of archived products so the summary's asset total stays
    # consistent with the archived-excluded product/quantity figures.
    qs = InventoryAsset.objects.exclude(product__is_archived=True)
    if makerspace_id is None:
        excluded = (
            rbac.superadmin_hidden_makerspace_ids()
            | rbac.archived_makerspace_ids()
        )
        return qs.exclude(makerspace_id__in=excluded) if excluded else qs
    return qs.filter(makerspace_id=makerspace_id)


def _items(makerspace_id):
    qs = HardwareRequestItem.objects.select_related("request", "product").filter(product__is_archived=False)
    if makerspace_id is None:
        excluded = (
            rbac.superadmin_hidden_makerspace_ids()
            | rbac.archived_makerspace_ids()
        )
        return qs.exclude(request__makerspace_id__in=excluded) if excluded else qs
    return qs.filter(request__makerspace_id=makerspace_id)


def _requests(makerspace_id):
    qs = HardwareRequest.objects.all()
    if makerspace_id is None:
        excluded = (
            rbac.superadmin_hidden_makerspace_ids()
            | rbac.archived_makerspace_ids()
        )
        return qs.exclude(makerspace_id__in=excluded) if excluded else qs
    return qs.filter(makerspace_id=makerspace_id)


def _qr_events(makerspace_id):
    qs = QrScanEvent.objects.all()
    if makerspace_id is None:
        excluded = (
            rbac.superadmin_hidden_makerspace_ids()
            | rbac.archived_makerspace_ids()
        )
        return qs.exclude(makerspace_id__in=excluded) if excluded else qs
    return qs.filter(makerspace_id=makerspace_id)


def _apply_date_range(qs, field, date_range):
    if not date_range:
        return qs
    start, end = date_range
    if start is not None:
        qs = qs.filter(**{f"{field}__gte": start})
    if end is not None:
        qs = qs.filter(**{f"{field}__lt": end})
    return qs


def _value(source, key):
    return source[key] if isinstance(source, dict) else getattr(source, key)
