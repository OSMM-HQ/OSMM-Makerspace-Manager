from django.db.models import Count, Sum

from apps.accounts import rbac
from apps.boxes.models import QrScanEvent
from apps.hardware_requests.display import label_from_candidates, requester_label
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem
from apps.inventory.models import InventoryAsset, InventoryProduct


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


def report_data(report_key="summary", makerspace_id=None):
    if report_key == "summary":
        return _summary(makerspace_id)
    return {"rows": report_rows(report_key, makerspace_id)}


def report_rows(report_key, makerspace_id=None):
    aggregate = makerspace_id is None
    if report_key == "taken-items":
        return _taken_items(makerspace_id, aggregate)
    if report_key == "active-loans":
        return _active_loans(makerspace_id, aggregate)
    if report_key == "returns":
        return _returns(makerspace_id, aggregate)
    if report_key == "damaged-missing":
        return _damaged_missing(makerspace_id, aggregate)
    if report_key == "damaged-lost":
        return _damaged_lost(makerspace_id, aggregate)
    if report_key == "qr-scans":
        return _qr_scans(makerspace_id, aggregate)
    if report_key == "most-lent":
        return _most_lent(makerspace_id, aggregate)
    if report_key == "top-borrowers":
        return _top_borrowers(makerspace_id, aggregate)
    if report_key == "recently-added":
        return _recently_added(makerspace_id, aggregate)
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


def _taken_items(makerspace_id, aggregate):
    # Group by product_id (not name) so two distinct products sharing a name are not
    # merged — there is no unique (makerspace, name) constraint. Name stays the display column.
    group = ["product_id", "product__name"]
    display = ["product__name"]
    header = ["product", "issued_quantity"]
    if aggregate:
        group = ["request__makerspace_id", *group]
        display = ["request__makerspace_id", *display]
        header = ["makerspace_id", *header]
    qs = _items(makerspace_id).values(*group).annotate(quantity=Sum("issued_quantity")).order_by("-quantity")
    return [header, *[[_value(row, key) for key in display] + [row["quantity"] or 0] for row in qs]]


def _active_loans(makerspace_id, aggregate):
    header = ["id", "requester", "status", "issued_at"]
    if aggregate:
        header = ["makerspace_id", *header]
    qs = _requests(makerspace_id).select_related("requester").filter(
        status__in=[HardwareRequest.Status.ISSUED, HardwareRequest.Status.PARTIALLY_RETURNED]
    ).order_by("-issued_at")
    return [header, *[_request_row(request, aggregate, request.issued_at) for request in qs]]


def _returns(makerspace_id, aggregate):
    header = ["id", "requester", "status", "closed_at"]
    if aggregate:
        header = ["makerspace_id", *header]
    qs = _requests(makerspace_id).select_related("requester").filter(
        status__in=[HardwareRequest.Status.RETURNED, HardwareRequest.Status.CLOSED_WITH_ISSUE]
    ).order_by("-closed_at")
    return [header, *[_request_row(request, aggregate, request.closed_at) for request in qs]]


def _request_row(request, aggregate, timestamp):
    # Readable holder label (never the internal checkin_<hash>); matches the ledger.
    prefix = [request.makerspace_id] if aggregate else []
    return [*prefix, request.id, requester_label(request), request.status, timestamp]


def _damaged_missing(makerspace_id, aggregate):
    values = ["name", "damaged_quantity", "lost_quantity"]
    header = ["product", "damaged_quantity", "missing_quantity"]
    return _product_quantity_rows(makerspace_id, aggregate, values, header)


def _damaged_lost(makerspace_id, aggregate):
    values = ["name", "damaged_quantity", "lost_quantity"]
    header = ["product_name", "damaged_quantity", "lost_quantity"]
    return _product_quantity_rows(makerspace_id, aggregate, values, header)


def _qr_scans(makerspace_id, aggregate):
    values = ["context"]
    header = ["context", "count"]
    if aggregate:
        values = ["makerspace_id", *values]
        header = ["makerspace_id", *header]
    qs = _qr_events(makerspace_id).values(*values).annotate(count=Count("id")).order_by(*values)
    return [header, *[[_value(row, key) for key in values] + [row["count"]] for row in qs]]


def _most_lent(makerspace_id, aggregate):
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
        _items(makerspace_id)
        .filter(issued_quantity__gt=0)
        .values(*group)
        .annotate(
            times_lent=Count("request_id", distinct=True),
            total_quantity_lent=Sum("issued_quantity"),
        )
        .order_by("-times_lent", "-total_quantity_lent", "product__name")
    )
    return [
        header,
        *[
            [_value(row, key) for key in display]
            + [row["times_lent"], row["total_quantity_lent"] or 0]
            for row in qs
        ],
    ]


def _top_borrowers(makerspace_id, aggregate):
    # Group by the requester (PROTECT, non-nullable, so never collapses NULLs) and
    # resolve a readable holder label — never the internal checkin_<hash> username.
    values = [
        "request__requester_id",
        # Request-level Check-In username (from the Check-In service, stable per
        # account) is the most readable holder label — prefer it over the account's
        # hashed username / external id. Grouping by it alongside requester_id does
        # not fragment counts because it is constant for a given Check-In account.
        "request__requester_username",
        "request__requester__username",
        "request__requester__external_checkin_user_id",
    ]
    header = ["holder", "requests", "items_borrowed"]
    if aggregate:
        values = ["request__makerspace_id", *values]
        header = ["makerspace_id", *header]
    qs = (
        _items(makerspace_id)
        .filter(issued_quantity__gt=0)
        .values(*values)
        .annotate(
            requests=Count("request_id", distinct=True),
            items_borrowed=Sum("issued_quantity"),
        )
        # In aggregate mode order per makerspace first so each makerspace gets its
        # own ranking (the frontend renders a separate section per makerspace),
        # rather than one blended cross-OSMM leaderboard.
        .order_by(
            *(["request__makerspace_id"] if aggregate else []),
            "-requests",
            "-items_borrowed",
            "request__requester__username",
        )
    )
    rows = []
    for row in qs:
        holder = label_from_candidates(
            row["request__requester_username"],
            row["request__requester__external_checkin_user_id"],
            row["request__requester__username"],
        )
        prefix = [row["request__makerspace_id"]] if aggregate else []
        rows.append([*prefix, holder, row["requests"], row["items_borrowed"] or 0])
    return [header, *rows]


def _recently_added(makerspace_id, aggregate):
    values = ["name", "created_at", "total_quantity"]
    header = ["product_name", "created_at", "total_quantity"]
    if aggregate:
        values = ["makerspace_id", *values]
        header = ["makerspace_id", *header]
    qs = _products(makerspace_id).order_by("-created_at", "-id")
    return [header, *[[_value(product, key) for key in values] for product in qs]]


def _product_quantity_rows(makerspace_id, aggregate, values, header):
    if aggregate:
        values = ["makerspace_id", *values]
        header = ["makerspace_id", *header]
    qs = _products(makerspace_id).order_by("name")
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


def _value(source, key):
    return source[key] if isinstance(source, dict) else getattr(source, key)
