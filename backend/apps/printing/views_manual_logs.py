from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.makerspaces.models import Makerspace
from apps.printing import services_manual_logs
from apps.printing.models import FilamentSpool, ManualPrintLog, PrintPrinter
from apps.printing.serializers_manual_logs import ManualPrintLogSerializer
from apps.printing.views_common import ERROR_RESPONSES, _int_query_param
from apps.printing.views_printers import ManagedPrinterMixin
from apps.printing.workflow import InvalidTransition


@extend_schema(tags=["Printing"], summary="List or create manual 3D print logs")
class ManualPrintLogListCreateView(ManagedPrinterMixin, generics.ListCreateAPIView):
    serializer_class = ManualPrintLogSerializer

    def get_queryset(self):
        qs = self.scope_queryset(
            ManualPrintLog.objects.select_related(
                "printer",
                "filament_spool",
                "makerspace",
                "logged_by",
            )
        )
        printer_id = _int_query_param(self.request, "printer")
        if printer_id is not None:
            qs = qs.filter(printer_id=printer_id)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        makerspace_id = data["makerspace_id"]
        self.assert_can_manage_makerspace(makerspace_id)
        makerspace = get_object_or_404(Makerspace, pk=makerspace_id)
        printer = get_object_or_404(
            PrintPrinter,
            pk=data["printer_id"],
            makerspace=makerspace,
        )
        spool = get_object_or_404(
            FilamentSpool,
            pk=data["filament_spool_id"],
            makerspace=makerspace,
        )
        try:
            log = services_manual_logs.log_manual_print(
                request.user,
                makerspace,
                printer,
                spool,
                data["grams_used"],
                data["title"],
                data.get("note", ""),
                duration_minutes=data.get("duration_minutes", 0),
            )
        except InvalidTransition as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(
            ManualPrintLogSerializer(log).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        parameters=[
            OpenApiParameter("makerspace", int, OpenApiParameter.QUERY),
            OpenApiParameter("printer", int, OpenApiParameter.QUERY),
        ],
        responses={200: ManualPrintLogSerializer(many=True), **ERROR_RESPONSES},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        request=ManualPrintLogSerializer,
        responses={201: ManualPrintLogSerializer, **ERROR_RESPONSES},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
