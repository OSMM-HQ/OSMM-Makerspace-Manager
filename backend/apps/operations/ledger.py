from datetime import datetime, timezone

from django.db.models import F

from apps.accounts import rbac
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem
from apps.hardware_requests.self_checkout_models import PublicToolLoan


def ledger_rows(makerspace_id=None):
    floor = datetime.min.replace(tzinfo=timezone.utc)
    rows = _request_item_rows(makerspace_id)
    return sorted(rows, key=lambda row: row["since"] or floor, reverse=True)


def _request_item_rows(makerspace_id):
    # Everything currently OUT is captured by the outstanding items of ISSUED /
    # PARTIALLY_RETURNED requests. This single source covers reviewed-request loans,
    # public self-checkout, AND admin direct handouts — the latter two also create a
    # backing HardwareRequest (with real item rows + quantities) plus a PublicToolLoan.
    # Reporting per item avoids the bundled-loan undercount of a one-line-per-loan view.
    queryset = (
        HardwareRequestItem.objects.select_related(
            "product",
            "request",
            "request__public_tool_loan",
            "request__public_tool_loan__requester",
        )
        .filter(
            request__status__in=[
                HardwareRequest.Status.ISSUED,
                HardwareRequest.Status.PARTIALLY_RETURNED,
            ]
        )
        .annotate(
            outstanding=(
                F("issued_quantity")
                - F("returned_quantity")
                - F("damaged_quantity")
                - F("missing_quantity")
            )
        )
        .filter(outstanding__gt=0)
    )
    if makerspace_id is not None:
        queryset = queryset.filter(request__makerspace_id=makerspace_id)
    else:
        excluded = (
            rbac.superadmin_hidden_makerspace_ids()
            | rbac.archived_makerspace_ids()
        )
        if excluded:
            queryset = queryset.exclude(request__makerspace_id__in=excluded)

    rows = []
    for item in queryset.order_by("-request__issued_at", "request_id", "id"):
        loan = _safe_loan(item.request)
        rows.append(
            {
                "source": _source(loan),
                "item_name": item.product.name,
                "holder": loan.requester.username if loan else _request_holder(item.request),
                "quantity": item.outstanding,
                "since": item.request.issued_at,
                "due": (loan.due_at if loan else None) or item.request.return_due_at,
                "makerspace_id": item.request.makerspace_id,
                "reference_id": loan.id if loan else item.request_id,
                "status": item.request.status,
            }
        )
    return rows


def _safe_loan(request):
    try:
        return request.public_tool_loan
    except PublicToolLoan.DoesNotExist:
        return None


def _source(loan):
    if loan is None:
        return "request"
    if loan.source == PublicToolLoan.Source.PUBLIC_SELF_CHECKOUT:
        return "self_checkout"
    return "direct_handout"


def _request_holder(request):
    return (
        request.requester_username
        or request.requester_contact_email
        or request.requester_contact_phone
    )
