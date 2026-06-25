from datetime import datetime, time, timedelta

from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.accounts.models import User
from apps.makerspaces.guards import require_module
from apps.printing.permissions import CanManagePrinting
from apps.printing.reports import build_printing_report
from apps.printing.reports_serializers import PrintingReportSerializer
from apps.printing.serializers import ErrorSerializer

DATE_RANGE_PARAMETERS = [
    OpenApiParameter("start", OpenApiTypes.DATE, OpenApiParameter.QUERY),
    OpenApiParameter("end", OpenApiTypes.DATE, OpenApiParameter.QUERY),
]


ERROR_RESPONSES = {
    400: OpenApiResponse(ErrorSerializer, description="Invalid request."),
    401: OpenApiResponse(description="Authentication credentials were not provided."),
    403: OpenApiResponse(description="Permission denied."),
    404: OpenApiResponse(description="Not found."),
}


def _is_superadmin(user):
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "role", None) == User.Role.SUPERADMIN
    )


class MakerspacePrintingReportView(APIView):
    permission_classes = [CanManagePrinting]
    action = "reports"

    @extend_schema(
        tags=["Printing reports"],
        summary="Retrieve makerspace printing report",
        request=None,
        parameters=DATE_RANGE_PARAMETERS,
        responses={200: PrintingReportSerializer, **ERROR_RESPONSES},
    )
    def get(self, request, makerspace_id, *args, **kwargs):
        require_module(makerspace_id, "printing")
        # The hard-hide block makes rbac.can() return False for a global superadmin on a
        # hidden makerspace, so this falls through to a 403 — the honest status, since the
        # makerspace's existence isn't secret (it still shows as a slim row in the list).
        if not rbac.can(request.user, rbac.Action.MANAGE_PRINTING, makerspace_id):
            raise PermissionDenied()

        report = build_printing_report(makerspace_id=makerspace_id, date_range=_date_range(request))
        return Response(PrintingReportSerializer(report).data)


class SuperadminPrintingReportView(APIView):
    permission_classes = [CanManagePrinting]
    action = "reports"

    @extend_schema(
        tags=["Printing reports"],
        summary="Retrieve aggregate printing report",
        request=None,
        parameters=DATE_RANGE_PARAMETERS,
        responses={200: PrintingReportSerializer, **ERROR_RESPONSES},
    )
    def get(self, request, *args, **kwargs):
        if not _is_superadmin(request.user):
            raise PermissionDenied()

        report = build_printing_report(include_makerspace=True, date_range=_date_range(request))
        return Response(PrintingReportSerializer(report).data)


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
