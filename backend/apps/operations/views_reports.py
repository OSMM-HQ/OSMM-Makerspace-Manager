from datetime import datetime, time, timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff, require_action
from apps.makerspaces.guards import require_module
from apps.makerspaces.models import Makerspace
from apps.operations import accountability, reports
from apps.operations.report_exports import _csv_response, _xlsx_cell, _xlsx_response
from apps.operations.schemas_reports import ANALYTICS_REPORT_RESPONSE
from apps.operations.serializers import EmptySerializer, GenericObjectSerializer
from apps.operations.serializers_reports import ReportErrorSerializer
from apps.operations.serializers_reports_payments import PaymentReportFilterSerializer
from apps.payments.models import Payment


DATE_RANGE_PARAMETERS = [
    OpenApiParameter("start", OpenApiTypes.DATE, OpenApiParameter.QUERY),
    OpenApiParameter("end", OpenApiTypes.DATE, OpenApiParameter.QUERY),
]
PAYMENT_FILTER_PARAMETERS = [
    OpenApiParameter("status", OpenApiTypes.STR, OpenApiParameter.QUERY, enum=Payment.Status.values),
    OpenApiParameter("subject_type", OpenApiTypes.STR, OpenApiParameter.QUERY, enum=Payment.SubjectType.values),
]
PREVIEW_PARAMETERS = [
    OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY),
    *DATE_RANGE_PARAMETERS,
    *PAYMENT_FILTER_PARAMETERS,
]
ERROR_RESPONSES = {
    400: OpenApiResponse(ReportErrorSerializer, description="Invalid report request."),
    401: OpenApiResponse(ReportErrorSerializer, description="Authentication required."),
    403: OpenApiResponse(ReportErrorSerializer, description="Permission denied."),
    404: OpenApiResponse(ReportErrorSerializer, description="Makerspace or report not found."),
}
EXPORT_RESPONSES = {
    (200, "text/csv"): OpenApiTypes.STR,
    (200, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"): OpenApiTypes.BINARY,
    **ERROR_RESPONSES,
}


class AnalyticsView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = GenericObjectSerializer

    @extend_schema(
        tags=["Analytics"], summary="Get analytics report", request=None,
        parameters=PREVIEW_PARAMETERS,
        responses={200: ANALYTICS_REPORT_RESPONSE, **ERROR_RESPONSES},
    )
    def get(self, request, makerspace_id, report_key="summary", *args, **kwargs):
        makerspace = _makerspace_for_inventory_view(request.user, makerspace_id)
        definition = reports.validate_report_key(report_key)
        require_action(request.user, definition.required_action, makerspace.id)
        require_module(makerspace, "reports")
        _require_source_modules(makerspace, definition.required_modules)
        return Response(reports.report_data(
            report_key, makerspace.id,
            limit=_limit_param(request), date_range=_date_range(request),
            report_filters=_report_filters(request, report_key),
        ))


class AccountabilityReportView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = GenericObjectSerializer

    @extend_schema(
        tags=["Analytics"], summary="Requester accountability dashboard",
        request=None, responses={200: OpenApiTypes.OBJECT, **ERROR_RESPONSES},
    )
    def get(self, request, makerspace_id, *args, **kwargs):
        makerspace = _makerspace_for_inventory_view(request.user, makerspace_id)
        require_action(request.user, rbac.Action.VIEW_AUDIT, makerspace.id)
        require_module(makerspace, "reports")
        return Response(accountability.accountability_data(makerspace.id))


class AggregateAnalyticsView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = GenericObjectSerializer

    @extend_schema(
        tags=["Analytics"], summary="Get aggregate analytics report", request=None,
        parameters=[
            OpenApiParameter("report_key", OpenApiTypes.STR, OpenApiParameter.PATH, enum=reports.REPORT_KEYS),
            *PREVIEW_PARAMETERS,
        ],
        responses={200: ANALYTICS_REPORT_RESPONSE, **ERROR_RESPONSES},
    )
    def get(self, request, report_key="summary", *args, **kwargs):
        _require_superadmin(request.user)
        reports.validate_report_key(report_key)
        return Response(reports.report_data(
            report_key, limit=_limit_param(request), date_range=_date_range(request),
            report_filters=_report_filters(request, report_key),
        ))


class ReportExportView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = EmptySerializer

    @extend_schema(
        tags=["Reports"], summary="Export report", request=None,
        parameters=[
            OpenApiParameter("report_key", OpenApiTypes.STR, OpenApiParameter.PATH, enum=reports.REPORT_KEYS),
            OpenApiParameter("format", OpenApiTypes.STR, OpenApiParameter.QUERY, enum=["csv", "xlsx"]),
            *DATE_RANGE_PARAMETERS,
            *PAYMENT_FILTER_PARAMETERS,
        ],
        responses=EXPORT_RESPONSES,
    )
    def get(self, request, makerspace_id, report_key, *args, **kwargs):
        makerspace = _makerspace_for_inventory_view(request.user, makerspace_id)
        definition = reports.validate_report_key(report_key, for_export=True)
        require_action(request.user, definition.required_action, makerspace.id)
        require_module(makerspace, "reports")
        _require_source_modules(makerspace, definition.required_modules)
        fmt = _export_format(request)
        rows = reports.report_rows(
            report_key, makerspace.id, date_range=_date_range(request),
            report_filters=_report_filters(request, report_key),
        )
        return _xlsx_response(rows, f"{report_key}.xlsx") if fmt == "xlsx" else _csv_response(rows, f"{report_key}.csv")


class AggregateReportExportView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = EmptySerializer

    @extend_schema(
        tags=["Reports"], summary="Export aggregate report", request=None,
        parameters=[
            OpenApiParameter("report_key", OpenApiTypes.STR, OpenApiParameter.PATH, enum=reports.REPORT_KEYS),
            OpenApiParameter("format", OpenApiTypes.STR, OpenApiParameter.QUERY, enum=["csv", "xlsx"]),
            *DATE_RANGE_PARAMETERS,
            *PAYMENT_FILTER_PARAMETERS,
        ],
        responses=EXPORT_RESPONSES,
    )
    def get(self, request, report_key, *args, **kwargs):
        _require_superadmin(request.user)
        reports.validate_report_key(report_key, for_export=True)
        fmt = _export_format(request)
        rows = reports.report_rows(
            report_key, date_range=_date_range(request),
            report_filters=_report_filters(request, report_key),
        )
        return _xlsx_response(rows, f"{report_key}.xlsx") if fmt == "xlsx" else _csv_response(rows, f"{report_key}.csv")


def report_data(makerspace_id, report_key):
    return reports.report_data(report_key, makerspace_id)


def report_rows(makerspace_id, report_key):
    return reports.report_rows(report_key, makerspace_id)


def _require_source_modules(makerspace, modules):
    for module in modules:
        require_module(makerspace, module)


def _date_range(request):
    start = _date_param(request, "start")
    end = _date_param(request, "end")
    if start and end and start > end:
        raise ValidationError({"end": "End date must be on or after start date."})
    start_dt = timezone.make_aware(datetime.combine(start, time.min)) if start else None
    end_dt = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min)) if end else None
    return (start_dt, end_dt) if start_dt or end_dt else None


def _date_param(request, name):
    raw = (request.query_params.get(name) or "").strip()
    if not raw:
        return None
    parsed = parse_date(raw)
    if parsed is None:
        raise ValidationError({name: "Use YYYY-MM-DD."})
    return parsed


def _makerspace_for_inventory_view(user, makerspace_id):
    queryset = rbac.scope_by_action(
        user, rbac.Action.VIEW_INVENTORY, Makerspace.objects.all(), field="id"
    )
    queryset = rbac.hide_from_superadmin(user, queryset, field="id")
    return get_object_or_404(queryset, pk=makerspace_id)


def _require_superadmin(user):
    if not (user.is_superuser or user.role == user.Role.SUPERADMIN):
        raise PermissionDenied()


def _export_format(request):
    fmt = (request.query_params.get("format") or "csv").strip().lower()
    if fmt not in {"csv", "xlsx"}:
        raise ValidationError({"format": "Use csv or xlsx."})
    return fmt


def _positive_int_param(request, name, default, maximum):
    raw = request.query_params.get(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError({name: "Enter a positive integer."}) from exc
    if value < 1:
        raise ValidationError({name: "Enter a positive integer."})
    return min(value, maximum)


def _page_params(request):
    return (_positive_int_param(request, "page", 1, 1000000), _positive_int_param(request, "page_size", 100, 500))


def _limit_param(request):
    return _positive_int_param(request, "limit", reports.DEFAULT_REPORT_LIMIT, reports.MAX_REPORT_LIMIT)


def _report_filters(request, report_key):
    if report_key != "payment-reconciliation":
        return {}
    serializer = PaymentReportFilterSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data
