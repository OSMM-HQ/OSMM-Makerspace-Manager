from django.db.models import Prefetch, Q
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts import rbac
from apps.audit import services as audit
from apps.makerspaces.guards import require_module
from apps.printing.models import FilamentSpool, PrintPrinter, PrintRequest
from apps.printing.permissions import CanManagePrinting
from apps.printing.serializers import PrintPrinterSerializer
from apps.printing.views_common import ERROR_RESPONSES, _int_query_param


def _printer_queryset():
    active_spools = FilamentSpool.objects.filter(is_active=True).order_by(
        "-opened_at", "-created_at"
    )
    queue = PrintRequest.objects.filter(
        status__in=[PrintRequest.Status.ACCEPTED, PrintRequest.Status.PRINTING]
    )
    return PrintPrinter.objects.prefetch_related(
        Prefetch("filament_spools", queryset=active_spools, to_attr="_active_spools"),
        Prefetch("print_requests", queryset=queue, to_attr="_queue_requests"),
    )


class ManagedPrinterMixin:
    permission_classes = [CanManagePrinting]
    action = "printer_admin"

    def scope_queryset(self, qs, field="makerspace_id"):
        qs = rbac.scope_by_action(
            self.request.user,
            rbac.Action.MANAGE_PRINTING,
            qs,
            field,
        )
        makerspace_id = _int_query_param(self.request, "makerspace")
        if makerspace_id is not None:
            require_module(makerspace_id, "printing")
            qs = qs.filter(makerspace_id=makerspace_id)
        return qs

    def assert_can_manage_makerspace(self, makerspace_id):
        require_module(makerspace_id, "printing")
        if not rbac.can(self.request.user, rbac.Action.MANAGE_PRINTING, makerspace_id):
            raise ValidationError({"makerspace": "You cannot manage printing here."})


@extend_schema(tags=["Printing"], summary="List or create managed 3D printers")
class ManagedPrinterListCreateView(ManagedPrinterMixin, generics.ListCreateAPIView):
    serializer_class = PrintPrinterSerializer

    def get_queryset(self):
        return self.scope_queryset(_printer_queryset())

    def perform_create(self, serializer):
        makerspace_id = serializer.validated_data["makerspace_id"]
        self.assert_can_manage_makerspace(makerspace_id)
        serializer.save()

    @extend_schema(
        parameters=[OpenApiParameter("makerspace", int, OpenApiParameter.QUERY)],
        responses={200: PrintPrinterSerializer(many=True), **ERROR_RESPONSES},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        request=PrintPrinterSerializer,
        responses={201: PrintPrinterSerializer, **ERROR_RESPONSES},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


@extend_schema(tags=["Printing"], summary="Retrieve, update, or delete managed 3D printer")
class ManagedPrinterDetailView(ManagedPrinterMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PrintPrinterSerializer

    def get_queryset(self):
        return self.scope_queryset(_printer_queryset())

    def perform_update(self, serializer):
        makerspace_id = serializer.validated_data.get(
            "makerspace_id", serializer.instance.makerspace_id
        )
        self.assert_can_manage_makerspace(makerspace_id)
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        # Hard-delete is allowed even when the printer is referenced by HISTORY: the
        # FKs on PrintRequest.printer / FilamentSpool.printer are SET_NULL, so past
        # rows survive (their printer field just clears) and history is never lost.
        # The one exception is an IN-PROGRESS job: deleting a printer mid-print would
        # strip attribution from a running request, so block that with a 409.
        printer = self.get_object()
        self.assert_can_manage_makerspace(printer.makerspace_id)
        if PrintRequest.objects.filter(
            Q(printer=printer) | Q(filament_spool__printer=printer),
            status=PrintRequest.Status.PRINTING,
        ).exists():
            return Response(
                {
                    "detail": (
                        "This printer has a print job in progress. Wait for it to "
                        "finish (or mark it failed) before deleting the printer."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        audit.record(
            request.user,
            "printing.printer_deleted",
            makerspace=printer.makerspace,
            target=printer,
        )
        printer.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses={200: PrintPrinterSerializer, **ERROR_RESPONSES})
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        request=PrintPrinterSerializer,
        responses={200: PrintPrinterSerializer, **ERROR_RESPONSES},
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    @extend_schema(
        responses={
            204: None,
            409: OpenApiResponse(description="Printer is referenced by print requests or spools."),
            **ERROR_RESPONSES,
        }
    )
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)
