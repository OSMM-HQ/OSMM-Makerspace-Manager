"""Authenticated requester compatibility views for the B4 printing cutover."""

from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.makerspaces.guards import require_module
from apps.printing.emails import notify_print_status
from apps.printing.models import PrintRequest
from apps.printing.permissions import IsActiveRequester
from apps.printing import public_workflow
from apps.printing.serializers import PrintRequestCreateSerializer, PrintRequestSerializer
from apps.printing.views_common import ERROR_RESPONSES
from apps.printing.workflow import legacy_compatible_response


class PersonalPrintRequestQuerysetMixin:
    """Read each request from the source authoritative for its makerspace."""

    def get_queryset(self):
        return (
            PrintRequest.objects.select_related(
                "bucket__makerspace", "requester", "handled_by", "reprint_of"
            )
            .prefetch_related("files", "reprint_of__files")
            .filter(
                requester=self.request.user,
                bucket__makerspace__printing_cutover_state__kernel_authoritative_at__isnull=True,
            )
            .order_by("-created_at")
        )

    def get_kernel_queryset(self):
        from apps.machines.models import MachineServiceRequest

        return (
            MachineServiceRequest.objects.select_related(
                "makerspace", "requester", "handled_by", "accepted_by", "reprint_of",
                "queue__machine_type", "assigned_machine", "run_consumable_pool",
            )
            .prefetch_related("files", "reprint_of__files")
            .filter(
                makerspace__archived_at__isnull=True,
                makerspace__printing_cutover_state__kernel_authoritative_at__isnull=False,
                queue__legacy_print_bucket_id__isnull=False,
                queue__machine_type__slug="3d_printer",
            )
            # Member is the canonical service-domain owner. Imported B4
            # history predates it, so retain requester ownership for only
            # those null-member rows.
            .filter(Q(member=self.request.user) | Q(member__isnull=True, requester=self.request.user))
            .order_by("-created_at")
        )

    def personal_print_requests(self):
        return sorted(
            [
                *self.get_queryset(),
                *(legacy_compatible_response(row, identifier=-row.pk) for row in self.get_kernel_queryset()),
            ],
            key=lambda row: row.created_at,
            reverse=True,
        )

    def get_personal_print_request(self, raw_pk):
        try:
            pk = int(raw_pk)
        except (TypeError, ValueError) as exc:
            raise NotFound() from exc
        if pk < 0:
            kernel = self.get_kernel_queryset().filter(pk=-pk).first()
            if kernel is None:
                raise NotFound()
            return legacy_compatible_response(kernel, identifier=pk)
        legacy = self.get_queryset().filter(pk=pk).first()
        if legacy is None:
            raise NotFound()
        return legacy


@extend_schema(tags=["Printing"], summary="List or create personal print requests")
class PrintRequestCreateListView(PersonalPrintRequestQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [IsActiveRequester]

    def get_serializer_class(self):
        return PrintRequestCreateSerializer if self.request.method == "POST" else PrintRequestSerializer

    @extend_schema(responses={200: PrintRequestSerializer(many=True), **ERROR_RESPONSES})
    def get(self, request, *args, **kwargs):
        rows = self.personal_print_requests()
        page = self.paginate_queryset(rows)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(rows, many=True).data)

    @extend_schema(request=PrintRequestCreateSerializer, responses={201: PrintRequestSerializer, **ERROR_RESPONSES})
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        makerspace = data["bucket"].makerspace
        require_module(makerspace, "printing")
        if public_workflow.kernel_is_authoritative(makerspace):
            unsupported = [
                field for field in ("model_file", "estimate_screenshot", "preview_screenshot")
                if data.get(field)
            ]
            if unsupported:
                raise serializers.ValidationError({
                    field: "Use the public upload flow for files after printing cutover."
                    for field in unsupported
                })
            kernel = public_workflow.submit_public_print_request(makerspace, {
                "bucket_id": data["bucket"].pk,
                "title": data["title"],
                "description": data.get("description", ""),
                "material": data.get("material", ""),
                "color": data.get("color", ""),
                "quantity": data.get("quantity", 1),
                "source_link": data.get("source_link", ""),
                "preferred_settings": data.get("preferred_settings", ""),
            }, request.user)
            instance = legacy_compatible_response(kernel, identifier=-kernel.pk)
            return Response(
                PrintRequestSerializer(instance, context=self.get_serializer_context()).data,
                status=status.HTTP_201_CREATED,
            )
        instance = serializer.save()
        notify_print_status(instance, "submitted")
        return Response(PrintRequestSerializer(instance, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Printing"], summary="Retrieve personal print request")
class PrintRequestDetailView(PersonalPrintRequestQuerysetMixin, generics.RetrieveAPIView):
    permission_classes = [IsActiveRequester]
    serializer_class = PrintRequestSerializer

    @extend_schema(responses={200: PrintRequestSerializer, **ERROR_RESPONSES})
    def get(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_personal_print_request(kwargs["pk"])).data)
