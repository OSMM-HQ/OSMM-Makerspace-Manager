from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.audit import services as audit
from apps.printing.models import FilamentSpool, PrintRequest
from apps.printing.serializers import FilamentSpoolSerializer
from apps.printing.views_common import ERROR_RESPONSES, _int_query_param
from apps.printing.views_printers import ManagedPrinterMixin


@extend_schema(tags=["Printing"], summary="List or create managed filament spools")
class ManagedFilamentSpoolListCreateView(
    ManagedPrinterMixin, generics.ListCreateAPIView
):
    serializer_class = FilamentSpoolSerializer

    def get_queryset(self):
        qs = self.scope_queryset(
            FilamentSpool.objects.select_related("printer", "makerspace")
        )
        printer_id = _int_query_param(self.request, "printer")
        if printer_id is not None:
            qs = qs.filter(printer_id=printer_id)
        return qs

    def perform_create(self, serializer):
        makerspace_id = serializer.validated_data["makerspace_id"]
        self.assert_can_manage_makerspace(makerspace_id)
        serializer.save()

    @extend_schema(
        parameters=[
            OpenApiParameter("makerspace", int, OpenApiParameter.QUERY),
            OpenApiParameter("printer", int, OpenApiParameter.QUERY),
        ],
        responses={200: FilamentSpoolSerializer(many=True), **ERROR_RESPONSES},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        request=FilamentSpoolSerializer,
        responses={201: FilamentSpoolSerializer, **ERROR_RESPONSES},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


@extend_schema(tags=["Printing"], summary="Retrieve or update managed filament spool")
class ManagedFilamentSpoolDetailView(
    ManagedPrinterMixin, generics.RetrieveUpdateDestroyAPIView
):
    serializer_class = FilamentSpoolSerializer

    def get_queryset(self):
        return self.scope_queryset(
            FilamentSpool.objects.select_related("printer", "makerspace")
        )

    def perform_update(self, serializer):
        makerspace_id = serializer.validated_data.get(
            "makerspace_id", serializer.instance.makerspace_id
        )
        self.assert_can_manage_makerspace(makerspace_id)
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        spool = self.get_object()
        self.assert_can_manage_makerspace(spool.makerspace_id)
        if PrintRequest.objects.filter(
            Q(filament_spool=spool) | Q(requested_filament_spool=spool)
        ).exists():
            return Response(
                {
                    "detail": (
                        "This spool is linked to print requests; deactivate it instead "
                        "to preserve history."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        audit.record(
            request.user,
            "print.spool_deleted",
            makerspace=spool.makerspace,
            target=spool,
        )
        spool.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses={200: FilamentSpoolSerializer, **ERROR_RESPONSES})
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        request=FilamentSpoolSerializer,
        responses={200: FilamentSpoolSerializer, **ERROR_RESPONSES},
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    @extend_schema(
        responses={
            204: None,
            409: OpenApiResponse(description="Spool is referenced by print requests."),
            **ERROR_RESPONSES,
        }
    )
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)
