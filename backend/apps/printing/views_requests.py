from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.evidence.storage import StorageUnavailable
from apps.makerspaces.guards import require_module
from apps.printing.emails import queue_staff_print_email
from apps.printing.models import PrintRequest, PrintRequestFile
from apps.printing.permissions import CanManagePrinting, IsActiveRequester
from apps.printing.serializers import (
    ErrorSerializer,
    ManagedPrintRequestSerializer,
    PrintRequestCreateSerializer,
    PrintRequestSerializer,
)
from apps.printing.storage import print_get_url
from apps.printing.views_common import ERROR_RESPONSES, _int_query_param


class PrintFileUrlResponseSerializer(serializers.Serializer):
    url = serializers.URLField()


@extend_schema(tags=["Printing"], summary="List or create personal print requests")
class PrintRequestCreateListView(generics.ListCreateAPIView):
    permission_classes = [IsActiveRequester]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return PrintRequestCreateSerializer
        return PrintRequestSerializer

    def get_queryset(self):
        return (
            PrintRequest.objects.select_related(
                "bucket__makerspace", "requester", "handled_by", "reprint_of"
            )
            .prefetch_related("files", "reprint_of__files")
            .filter(requester=self.request.user)
            .order_by("-created_at")
        )

    @extend_schema(responses={200: PrintRequestSerializer(many=True), **ERROR_RESPONSES})
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        request=PrintRequestCreateSerializer,
        responses={201: PrintRequestSerializer, **ERROR_RESPONSES},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        require_module(serializer.validated_data["bucket"].makerspace, "printing")
        instance = serializer.save()
        queue_staff_print_email("submitted", instance.pk)
        return Response(
            PrintRequestSerializer(instance, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Printing"], summary="Retrieve personal print request")
class PrintRequestDetailView(generics.RetrieveAPIView):
    permission_classes = [IsActiveRequester]
    serializer_class = PrintRequestSerializer

    def get_queryset(self):
        return (
            PrintRequest.objects.select_related(
                "bucket__makerspace", "requester", "handled_by", "reprint_of"
            )
            .prefetch_related("files", "reprint_of__files")
            .filter(requester=self.request.user)
            .order_by("-created_at")
        )

    @extend_schema(responses={200: PrintRequestSerializer, **ERROR_RESPONSES})
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ManagedPrintRequestQuerysetMixin:
    def get_queryset(self):
        qs = PrintRequest.objects.select_related(
            "bucket__makerspace", "requester", "handled_by", "reprint_of"
        ).prefetch_related("files", "reprint_of__files").order_by("-created_at")
        qs = rbac.scope_by_action(
            self.request.user,
            rbac.Action.MANAGE_PRINTING,
            qs,
            "bucket__makerspace_id",
        )

        makerspace_id = _int_query_param(self.request, "makerspace")
        if makerspace_id is not None:
            require_module(makerspace_id, "printing")
            qs = qs.filter(bucket__makerspace_id=makerspace_id)
        else:
            qs = rbac.hide_from_superadmin(
                self.request.user,
                qs,
                "bucket__makerspace_id",
            )

        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        bucket_id = _int_query_param(self.request, "bucket")
        if bucket_id is not None:
            qs = qs.filter(bucket_id=bucket_id)

        return qs


@extend_schema(tags=["Printing"], summary="List managed print requests")
class ManagedPrintRequestListView(
    ManagedPrintRequestQuerysetMixin, generics.ListAPIView
):
    permission_classes = [CanManagePrinting]
    serializer_class = ManagedPrintRequestSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter("makerspace", int, OpenApiParameter.QUERY),
            OpenApiParameter("status", str, OpenApiParameter.QUERY),
            OpenApiParameter("bucket", int, OpenApiParameter.QUERY),
        ],
        responses={200: ManagedPrintRequestSerializer(many=True), **ERROR_RESPONSES},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


@extend_schema(tags=["Printing"], summary="Retrieve managed print request")
class ManagedPrintRequestDetailView(
    ManagedPrintRequestQuerysetMixin, generics.RetrieveAPIView
):
    permission_classes = [CanManagePrinting]
    serializer_class = ManagedPrintRequestSerializer

    @extend_schema(responses={200: ManagedPrintRequestSerializer, **ERROR_RESPONSES})
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


@extend_schema(tags=["Printing"], summary="Get a signed view URL for a print request file")
class ManagedPrintFileUrlView(APIView):
    permission_classes = [CanManagePrinting]

    @extend_schema(
        responses={
            200: PrintFileUrlResponseSerializer,
            503: OpenApiResponse(
                ErrorSerializer, description="Storage is unavailable."
            ),
            **ERROR_RESPONSES,
        }
    )
    def get(self, request, pk):
        # Only files attached to a submitted request are exposable; unattached staging
        # rows (a public user uploaded but never submitted) have print_request=None and
        # must never get a signed URL.
        qs = rbac.scope_by_action(
            request.user,
            rbac.Action.MANAGE_PRINTING,
            PrintRequestFile.objects.filter(print_request__isnull=False),
            "makerspace_id",
        )
        print_file = get_object_or_404(qs, pk=pk)
        require_module(print_file.makerspace_id, "printing")
        try:
            url = print_get_url(
                print_file.object_key,
                filename=print_file.original_filename or "",
                content_type=print_file.content_type or "",
                as_attachment=(print_file.kind != "screenshot"),
                kind=print_file.kind,
            )
        except StorageUnavailable:
            return Response(
                {"detail": "Storage is unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"url": url})


@extend_schema(tags=["Printing"], summary="List completed print requests")
class PrintedListView(ManagedPrintRequestQuerysetMixin, generics.ListAPIView):
    permission_classes = [CanManagePrinting]
    serializer_class = ManagedPrintRequestSerializer

    def get_queryset(self):
        return super().get_queryset().filter(status=PrintRequest.Status.COMPLETED)

    @extend_schema(
        parameters=[
            OpenApiParameter("makerspace", int, OpenApiParameter.QUERY),
            OpenApiParameter("bucket", int, OpenApiParameter.QUERY),
        ],
        responses={200: ManagedPrintRequestSerializer(many=True), **ERROR_RESPONSES},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
