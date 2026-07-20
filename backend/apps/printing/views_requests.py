from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.evidence.storage import StorageUnavailable
from apps.makerspaces.guards import require_module
from apps.printing.models import FilamentSpool, PrintRequest, PrintRequestFile
from apps.printing.permissions import CanManagePrinting
from apps.printing.serializers import (
    ErrorSerializer,
    ManagedPrintRequestSerializer,
    PrintRequestSerializer,
)
from apps.printing.storage import print_get_url
from apps.printing.views_common import ERROR_RESPONSES, _int_query_param
from apps.printing.workflow import legacy_compatible_response


class PrintFileUrlResponseSerializer(serializers.Serializer):
    url = serializers.URLField()


class ManagedPrintRequestQuerysetMixin:
    def get_queryset(self):
        active_spools = FilamentSpool.objects.filter(is_active=True).order_by(
            "-opened_at", "-created_at"
        )
        queue = PrintRequest.objects.filter(
            status__in=[PrintRequest.Status.ACCEPTED, PrintRequest.Status.PRINTING]
        )
        qs = PrintRequest.objects.select_related(
            "bucket__makerspace",
            "requester",
            "handled_by",
            "accepted_by",
            "reprint_of",
            "printer",
            "filament_spool",
            "requested_filament_spool",
        ).prefetch_related(
            "files",
            "reprint_of__files",
            Prefetch("printer__filament_spools", queryset=active_spools, to_attr="_active_spools"),
            Prefetch("printer__print_requests", queryset=queue, to_attr="_queue_requests"),
        ).order_by("-created_at")
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

        return qs.filter(
            bucket__makerspace__printing_cutover_state__kernel_authoritative_at__isnull=True,
        )

    def get_kernel_queryset(self):
        """Authoritative printer queue rows projected onto the print-manager API."""
        from apps.machines.models import MachineServiceRequest

        qs = MachineServiceRequest.objects.select_related(
            "makerspace", "requester", "handled_by", "accepted_by", "reprint_of",
            "queue__machine_type", "assigned_machine", "run_consumable_pool",
        ).prefetch_related("files", "reprint_of__files").filter(
            makerspace__printing_cutover_state__kernel_authoritative_at__isnull=False,
            queue__legacy_print_bucket_id__isnull=False,
            queue__machine_type__slug="3d_printer",
        ).order_by("-created_at")
        qs = rbac.scope_by_action(
            self.request.user, rbac.Action.MANAGE_PRINTING, qs, "makerspace_id",
        )
        makerspace_id = _int_query_param(self.request, "makerspace")
        if makerspace_id is not None:
            require_module(makerspace_id, "printing")
            qs = qs.filter(makerspace_id=makerspace_id)
        else:
            qs = rbac.hide_from_superadmin(self.request.user, qs, "makerspace_id")
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=("in_progress" if status_filter == PrintRequest.Status.PRINTING else status_filter))
        bucket_id = _int_query_param(self.request, "bucket")
        if bucket_id is not None:
            qs = qs.filter(queue__legacy_print_bucket_id=bucket_id)
        return qs

    def get_object(self):
        try:
            pk = int(self.kwargs["pk"])
        except (TypeError, ValueError) as exc:
            raise Http404 from exc
        if pk < 0:
            kernel = self.get_kernel_queryset().filter(pk=-pk).first()
            if kernel is None:
                raise Http404
            return legacy_compatible_response(kernel, identifier=pk)
        legacy = self.get_queryset().filter(pk=pk).first()
        if legacy is not None:
            return legacy
        raise Http404

    def managed_print_requests(self):
        return sorted(
            [*self.get_queryset(), *(legacy_compatible_response(row, identifier=-row.pk) for row in self.get_kernel_queryset())],
            key=lambda row: row.created_at,
            reverse=True,
        )


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
        rows = self.managed_print_requests()
        page = self.paginate_queryset(rows)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(rows, many=True).data)


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
        try:
            file_id = int(pk)
        except (TypeError, ValueError) as exc:
            raise Http404 from exc
        qs = rbac.scope_by_action(
            request.user,
            rbac.Action.MANAGE_PRINTING,
            PrintRequestFile.objects.filter(print_request__isnull=False),
            "makerspace_id",
        )
        print_file = qs.filter(pk=file_id).first() if file_id > 0 else None
        if file_id < 0:
            # Kernel-created print requests retain their files only in the
            # service domain.  The same Print Manager action and route owns
            # them, scoped to reconciled printer queues.
            from apps.machines.models import ServiceRequestFile

            kernel_files = ServiceRequestFile.objects.filter(
                service_request__makerspace__printing_cutover_state__kernel_authoritative_at__isnull=False,
                service_request__queue__legacy_print_bucket_id__isnull=False,
                service_request__queue__machine_type__slug="3d_printer",
            )
            kernel_files = rbac.scope_by_action(
                request.user, rbac.Action.MANAGE_PRINTING, kernel_files, "makerspace_id",
            )
            print_file = get_object_or_404(kernel_files, pk=-file_id)
        elif print_file is None:
            raise Http404
        require_module(print_file.makerspace_id, "printing")
        try:
            url = print_get_url(
                print_file.object_key,
                filename=print_file.original_filename or "",
                content_type=print_file.content_type or "",
                as_attachment=(print_file.kind != "screenshot"),
                kind="stl" if print_file.kind == "model" else print_file.kind,
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

    def managed_print_requests(self):
        rows = super().managed_print_requests()
        return [row for row in rows if row.status == PrintRequest.Status.COMPLETED]

    @extend_schema(
        parameters=[
            OpenApiParameter("makerspace", int, OpenApiParameter.QUERY),
            OpenApiParameter("bucket", int, OpenApiParameter.QUERY),
        ],
        responses={200: ManagedPrintRequestSerializer(many=True), **ERROR_RESPONSES},
    )
    def get(self, request, *args, **kwargs):
        rows = self.managed_print_requests()
        page = self.paginate_queryset(rows)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(rows, many=True).data)
