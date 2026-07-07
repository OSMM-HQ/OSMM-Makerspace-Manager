from datetime import datetime, timezone

from django.db.models import (
    BooleanField,
    Case,
    CharField,
    DateTimeField,
    Exists,
    F,
    IntegerField,
    OuterRef,
    Q,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.utils import timezone as django_timezone

from apps.accounts import rbac
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem
from apps.hardware_requests.self_checkout_models import PublicToolLoan
SOURCE_REVIEWED = "request"
SOURCE_SELF_CHECKOUT = "self_checkout"
SOURCE_DIRECT = "direct_handout"
SOURCE_QUERY_VALUES = {
    "reviewed": SOURCE_REVIEWED,
    "request": SOURCE_REVIEWED,
    "self_checkout": SOURCE_SELF_CHECKOUT,
    "direct": SOURCE_DIRECT,
    "direct_handout": SOURCE_DIRECT,
}
SORT_FIELDS = {
    "item_name": "ledger_item_name",
    "holder": "holder_sort",
    "quantity": "quantity",
    "since": "since_sort",
    "due": "due_sort",
    "source": "ledger_source",
    "makerspace_id": "ledger_makerspace_id",
}
LEDGER_COLUMNS = [
    "ledger_source",
    "ledger_item_name",
    "ledger_container",
    "holder_sort",
    "quantity",
    "ledger_target_label",
    "since",
    "due",
    "since_sort",
    "due_sort",
    "overdue",
    "ledger_makerspace_id",
    "reference_id",
    "ledger_status",
    "row_group",
    "ledger_request_id",
    "ledger_item_id",
    "ledger_product_id",
    "loan_id",
]
_FLOOR = datetime.min.replace(tzinfo=timezone.utc)
_CEILING = datetime.max.replace(tzinfo=timezone.utc)
def normalize_source(value):
    return SOURCE_QUERY_VALUES.get(value)

def normalize_sort(value):
    raw = (value or "").strip()
    if not raw:
        return None
    field = raw[1:] if raw.startswith("-") else raw
    return raw if field in SORT_FIELDS else None

def ordered_queryset(makerspace_id, *, filters=None):
    filters = filters or {}
    return _ledger_queryset(makerspace_id, filters).order_by(
        *_order_by(filters.get("sort"))
    )

def _ledger_queryset(makerspace_id, filters):
    item_rows = _filter_item_rows(_annotated_item_queryset(makerspace_id), filters)
    container_rows = _filter_container_rows(
        _annotated_container_queryset(makerspace_id), filters
    )
    return item_rows.values(*LEDGER_COLUMNS).union(
        container_rows.values(*LEDGER_COLUMNS),
        all=True,
    )

def _annotated_item_queryset(makerspace_id):
    return _request_item_queryset(makerspace_id).annotate(
        ledger_source=Case(
            When(request__public_tool_loan__isnull=True, then=Value(SOURCE_REVIEWED)),
            When(
                request__public_tool_loan__source=PublicToolLoan.Source.PUBLIC_SELF_CHECKOUT,
                then=Value(SOURCE_SELF_CHECKOUT),
            ),
            default=Value(SOURCE_DIRECT),
            output_field=CharField(),
        ),
        ledger_item_name=F("product__name"),
        ledger_container=Coalesce(
            "request__public_tool_loan__container__label",
            "request__assigned_box__label",
            output_field=CharField(),
        ),
        holder_sort=_holder_sort_annotation("request"),
        quantity=F("outstanding"),
        ledger_target_label=F("request__public_tool_loan__target_label"),
        since=F("request__issued_at"),
        due=Coalesce(
            "request__public_tool_loan__due_at",
            "request__return_due_at",
            output_field=DateTimeField(),
        ),
        since_sort=Coalesce(
            "request__issued_at", Value(_FLOOR), output_field=DateTimeField()
        ),
        due_sort=Coalesce(
            "request__public_tool_loan__due_at",
            "request__return_due_at",
            Value(_CEILING),
            output_field=DateTimeField(),
        ),
        overdue=Case(
            When(
                Q(request__public_tool_loan__due_at__lt=django_timezone.now())
                | Q(
                    request__public_tool_loan__due_at__isnull=True,
                    request__return_due_at__lt=django_timezone.now(),
                ),
                then=Value(True),
            ),
            default=Value(False),
            output_field=BooleanField(),
        ),
        ledger_makerspace_id=F("request__makerspace_id"),
        reference_id=Coalesce(
            "request__public_tool_loan__id", "request_id", output_field=IntegerField()
        ),
        ledger_status=F("request__status"),
        row_group=Value(0, output_field=IntegerField()),
        ledger_item_id=F("id"),
        ledger_request_id=F("request_id"),
        ledger_product_id=F("product_id"),
        loan_id=F("request__public_tool_loan__id"),
    )

def _annotated_container_queryset(makerspace_id):
    return _container_only_loan_queryset(makerspace_id).annotate(
        ledger_source=Value(SOURCE_DIRECT, output_field=CharField()),
        ledger_item_name=F("container__label"),
        ledger_container=Value(None, output_field=CharField()),
        holder_sort=_holder_sort_annotation("request"),
        quantity=Value(1, output_field=IntegerField()),
        ledger_target_label=Value(None, output_field=CharField()),
        since=Coalesce("checked_out_at", "request__issued_at", output_field=DateTimeField()),
        due=F("due_at"),
        since_sort=Coalesce(
            "checked_out_at",
            "request__issued_at",
            Value(_FLOOR),
            output_field=DateTimeField(),
        ),
        due_sort=Coalesce("due_at", Value(_CEILING), output_field=DateTimeField()),
        overdue=Case(
            When(due_at__lt=django_timezone.now(), then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        ),
        ledger_makerspace_id=F("makerspace_id"),
        reference_id=F("id"),
        ledger_status=F("request__status"),
        row_group=Value(1, output_field=IntegerField()),
        ledger_request_id=F("request_id"),
        ledger_item_id=Value(None, output_field=IntegerField()),
        ledger_product_id=Value(None, output_field=IntegerField()),
        loan_id=F("id"),
    )

def _request_item_queryset(makerspace_id):
    queryset = (
        HardwareRequestItem.objects.filter(
            request__status__in=[
                HardwareRequest.Status.ISSUED,
                HardwareRequest.Status.PARTIALLY_RETURNED,
            ]
        )
        .annotate(
            outstanding=F("issued_quantity")
            - F("returned_quantity")
            - F("damaged_quantity")
            - F("missing_quantity")
        )
        .filter(outstanding__gt=0)
    )
    if makerspace_id is not None:
        return queryset.filter(request__makerspace_id=makerspace_id)
    excluded = rbac.superadmin_hidden_makerspace_ids() | rbac.archived_makerspace_ids()
    return queryset.exclude(request__makerspace_id__in=excluded) if excluded else queryset

def _container_only_loan_queryset(makerspace_id):
    outstanding_items = (
        HardwareRequestItem.objects.filter(request_id=OuterRef("request_id"))
        .annotate(
            outstanding=F("issued_quantity")
            - F("returned_quantity")
            - F("damaged_quantity")
            - F("missing_quantity")
        )
        .filter(outstanding__gt=0)
    )
    queryset = (
        PublicToolLoan.objects.filter(
            source=PublicToolLoan.Source.ADMIN_DIRECT,
            status=PublicToolLoan.Status.CHECKED_OUT,
            container__isnull=False,
        )
        .annotate(has_outstanding_items=Exists(outstanding_items))
        .filter(has_outstanding_items=False)
    )
    if makerspace_id is not None:
        return queryset.filter(makerspace_id=makerspace_id)
    excluded = rbac.superadmin_hidden_makerspace_ids() | rbac.archived_makerspace_ids()
    return queryset.exclude(makerspace_id__in=excluded) if excluded else queryset

def _filter_item_rows(queryset, filters):
    queryset = _filter_common(queryset, filters)
    search = (filters.get("search") or "").strip()
    if search:
        queryset = queryset.filter(
            _borrower_search_q("request", search)
            | Q(product__name__icontains=search)
            | Q(request__assigned_box__label__icontains=search)
            | Q(request__public_tool_loan__container__label__icontains=search)
        )
    return queryset

def _filter_container_rows(queryset, filters):
    source = filters.get("source")
    if source and source != SOURCE_DIRECT:
        queryset = queryset.none()
    queryset = _filter_common(queryset, {**filters, "source": None})
    search = (filters.get("search") or "").strip()
    if search:
        queryset = queryset.filter(
            _borrower_search_q("request", search) | Q(container__label__icontains=search)
        )
    return queryset

def _filter_common(queryset, filters):
    source = filters.get("source")
    if source:
        queryset = queryset.filter(ledger_source=source)
    overdue = filters.get("overdue")
    if overdue is not None:
        queryset = queryset.filter(overdue=overdue)
    return queryset

def _borrower_search_q(prefix, search):
    return (
        Q(**{f"{prefix}__requester_name__icontains": search})
        | Q(**{f"{prefix}__requester_contact_email__icontains": search})
        | Q(**{f"{prefix}__requester_contact_phone__icontains": search})
        | Q(**{f"{prefix}__requester_username__icontains": search})
        | Q(**{f"{prefix}__requester__email__icontains": search})
        | Q(**{f"{prefix}__requester__external_checkin_user_id__icontains": search})
        | Q(**{f"{prefix}__requester__username__icontains": search})
    )

def _holder_sort_annotation(prefix):
    return Case(
        When(**{f"{prefix}__requester_name__gt": "", "then": F(f"{prefix}__requester_name")}),
        When(**{f"{prefix}__requester_contact_email__contains": "@", "then": F(f"{prefix}__requester_contact_email")}),
        When(**{f"{prefix}__requester__email__contains": "@", "then": F(f"{prefix}__requester__email")}),
        When(**{f"{prefix}__requester_username__contains": "@", "then": F(f"{prefix}__requester_username")}),
        When(**{f"{prefix}__requester__external_checkin_user_id__contains": "@", "then": F(f"{prefix}__requester__external_checkin_user_id")}),
        When(**{f"{prefix}__requester_contact_phone__gt": "", "then": F(f"{prefix}__requester_contact_phone")}),
        When(**{f"{prefix}__requester_username__gt": "", "then": F(f"{prefix}__requester_username")}),
        When(**{f"{prefix}__requester__external_checkin_user_id__gt": "", "then": F(f"{prefix}__requester__external_checkin_user_id")}),
        When(**{f"{prefix}__requester__username__gt": "", "then": F(f"{prefix}__requester__username")}),
        default=Value("Member"),
        output_field=CharField(),
    )

def _order_by(sort):
    if sort:
        descending = sort.startswith("-")
        field = sort[1:] if descending else sort
        direction = "-" if descending else ""
        return [
            f"{direction}{SORT_FIELDS[field]}",
            "-since_sort",
            "row_group",
            "ledger_request_id",
            "ledger_item_id",
            "loan_id",
        ]
    return ["-since_sort", "row_group", "ledger_request_id", "ledger_item_id", "loan_id"]
