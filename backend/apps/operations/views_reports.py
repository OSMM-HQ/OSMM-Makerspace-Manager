import csv
from io import BytesIO, StringIO

from datetime import datetime, time, timedelta

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from openpyxl import Workbook
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff, require_action
from apps.makerspaces.guards import require_module
from apps.makerspaces.models import Makerspace
from apps.operations import accountability, ledger, reports
from apps.operations.serializers import EmptySerializer, GenericObjectSerializer, LedgerResponseSerializer

DATE_RANGE_PARAMETERS = [
    OpenApiParameter("start", OpenApiTypes.DATE, OpenApiParameter.QUERY),
    OpenApiParameter("end", OpenApiTypes.DATE, OpenApiParameter.QUERY),
]


class LedgerView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = LedgerResponseSerializer

    @extend_schema(
        tags=["Ledger"],
        summary="List outstanding inventory loans",
        request=None,
        parameters=[
            OpenApiParameter("page", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("page_size", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: LedgerResponseSerializer},
    )
    def get(self, request, makerspace_id, *args, **kwargs):
        makerspace = _makerspace_for_inventory_view(request.user, makerspace_id)
        require_action(request.user, rbac.Action.VIEW_INVENTORY, makerspace.id)
        require_module(makerspace, "staff_admin")
        return Response(_ledger_payload(makerspace.id, request))


class AggregateLedgerView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = LedgerResponseSerializer

    @extend_schema(
        tags=["Ledger"],
        summary="List outstanding inventory loans across all makerspaces",
        request=None,
        parameters=[
            OpenApiParameter("page", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("page_size", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: LedgerResponseSerializer},
    )
    def get(self, request, *args, **kwargs):
        _require_superadmin(request.user)
        return Response(_ledger_payload(None, request))


class AnalyticsView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = GenericObjectSerializer

    @extend_schema(
        tags=["Analytics"],
        summary="Get analytics report",
        request=None,
        parameters=[OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY), *DATE_RANGE_PARAMETERS],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, makerspace_id, report_key="summary", *args, **kwargs):
        makerspace = _makerspace_for_inventory_view(request.user, makerspace_id)
        require_action(request.user, rbac.Action.VIEW_AUDIT, makerspace.id)
        require_module(makerspace, "reports")
        return Response(reports.report_data(report_key, makerspace.id, limit=_limit_param(request), date_range=_date_range(request)))


class AccountabilityReportView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = GenericObjectSerializer

    @extend_schema(
        tags=["Analytics"],
        summary="Requester accountability dashboard",
        request=None,
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, makerspace_id, *args, **kwargs):
        makerspace = _makerspace_for_inventory_view(request.user, makerspace_id)
        require_action(request.user, rbac.Action.VIEW_AUDIT, makerspace.id)
        require_module(makerspace, "reports")
        return Response(accountability.accountability_data(makerspace.id))


class ProblemReportResolveView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = GenericObjectSerializer

    @extend_schema(
        tags=["Analytics"],
        summary="Resolve a public problem report",
        request=None,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, makerspace_id, pk, *args, **kwargs):
        from apps.audit import services as audit
        from apps.hardware_requests.models import PublicProblemReport

        makerspace = _makerspace_for_inventory_view(request.user, makerspace_id)
        require_action(request.user, rbac.Action.EDIT_INVENTORY, makerspace.id)
        require_module(makerspace, "reports")
        report = get_object_or_404(
            PublicProblemReport.objects.filter(makerspace_id=makerspace.id), pk=pk
        )
        if report.resolved_at is None:
            report.resolved_at = timezone.now()
            report.resolved_by = request.user
            report.save(update_fields=["resolved_at", "resolved_by"])
            audit.record(
                request.user,
                "public_problem.resolved",
                makerspace=makerspace,
                target=report,
                meta={"loan_id": report.loan_id},
            )
        return Response({"id": report.id, "resolved": True})


class AggregateAnalyticsView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = GenericObjectSerializer

    @extend_schema(
        tags=["Analytics"],
        summary="Get aggregate analytics report",
        request=None,
        parameters=[
            OpenApiParameter("report_key", OpenApiTypes.STR, OpenApiParameter.PATH, enum=reports.REPORT_KEYS),
            OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY),
            *DATE_RANGE_PARAMETERS,
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, report_key="summary", *args, **kwargs):
        _require_superadmin(request.user)
        return Response(reports.report_data(report_key, limit=_limit_param(request), date_range=_date_range(request)))


class ReportExportView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = EmptySerializer

    @extend_schema(
        tags=["Reports"],
        summary="Export report",
        request=None,
        parameters=[
            OpenApiParameter("report_key", OpenApiTypes.STR, OpenApiParameter.PATH, enum=reports.REPORT_KEYS),
            OpenApiParameter("format", OpenApiTypes.STR, OpenApiParameter.QUERY, enum=["csv", "xlsx"]),
            *DATE_RANGE_PARAMETERS,
        ],
        responses={
            (200, "text/csv"): OpenApiTypes.STR,
            (200, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"): OpenApiTypes.BINARY,
        },
    )
    def get(self, request, makerspace_id, report_key, *args, **kwargs):
        makerspace = _makerspace_for_inventory_view(request.user, makerspace_id)
        require_action(request.user, rbac.Action.VIEW_AUDIT, makerspace.id)
        require_module(makerspace, "reports")
        fmt = request.query_params.get("format", "csv")
        rows = reports.report_rows(report_key, makerspace.id, date_range=_date_range(request))
        if fmt == "xlsx":
            return _xlsx_response(rows, f"{report_key}.xlsx")
        if fmt != "csv":
            raise ValidationError({"format": "Use csv or xlsx."})
        return _csv_response(rows, f"{report_key}.csv")


class AggregateReportExportView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = EmptySerializer

    @extend_schema(
        tags=["Reports"],
        summary="Export aggregate report",
        request=None,
        parameters=[
            OpenApiParameter("report_key", OpenApiTypes.STR, OpenApiParameter.PATH, enum=reports.REPORT_KEYS),
            OpenApiParameter("format", OpenApiTypes.STR, OpenApiParameter.QUERY, enum=["csv", "xlsx"]),
            *DATE_RANGE_PARAMETERS,
        ],
        responses={
            (200, "text/csv"): OpenApiTypes.STR,
            (200, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"): OpenApiTypes.BINARY,
        },
    )
    def get(self, request, report_key, *args, **kwargs):
        _require_superadmin(request.user)
        fmt = request.query_params.get("format", "csv")
        rows = reports.report_rows(report_key, date_range=_date_range(request))
        if fmt == "xlsx":
            return _xlsx_response(rows, f"{report_key}.xlsx")
        if fmt != "csv":
            raise ValidationError({"format": "Use csv or xlsx."})
        return _csv_response(rows, f"{report_key}.csv")


def report_data(makerspace_id, report_key):
    return reports.report_data(report_key, makerspace_id)


def report_rows(makerspace_id, report_key):
    return reports.report_rows(report_key, makerspace_id)


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
    queryset = rbac.scope_by_action(user, rbac.Action.VIEW_INVENTORY, Makerspace.objects.all(), field="id")
    # Soft-hide: a superadmin must not reach a makerspace that turned off superadmin
    # access by querying it directly by id (the aggregate paths already exclude it).
    # No-op for non-superadmins, so a hidden space's own staff keep their reports.
    queryset = rbac.hide_from_superadmin(user, queryset, field="id")
    return get_object_or_404(queryset, pk=makerspace_id)


def _require_superadmin(user):
    if not (user.is_superuser or user.role == user.Role.SUPERADMIN):
        raise PermissionDenied()


def _ledger_payload(makerspace_id, request):
    page, page_size = _page_params(request)
    payload = ledger.ledger_page(makerspace_id, page=page, page_size=page_size)
    serializer = LedgerResponseSerializer(payload)
    return serializer.data


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
    return (
        _positive_int_param(request, "page", 1, 1000000),
        _positive_int_param(request, "page_size", 100, 500),
    )


def _limit_param(request):
    return _positive_int_param(request, "limit", reports.DEFAULT_REPORT_LIMIT, reports.MAX_REPORT_LIMIT)


def _csv_response(rows, filename):
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerows([[_export_cell(value) for value in row] for row in rows])
    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _xlsx_response(rows, filename):
    wb = Workbook()
    ws = wb.active
    for row in rows:
        # openpyxl raises on tz-aware datetimes ("Excel does not support timezones");
        # report rows (e.g. active-loans issued_at, returns closed_at) carry aware
        # datetimes, so drop tzinfo before writing the cell.
        ws.append([_xlsx_cell(value) for value in row])
    buffer = BytesIO()
    wb.save(buffer)
    response = HttpResponse(buffer.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _xlsx_cell(value):
    from datetime import datetime as _dt

    if isinstance(value, _dt) and value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return _export_cell(value)


def _export_cell(value):
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{value}"
    return value
