from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts import rbac
from apps.printing import workflow
from apps.printing.models import FilamentSpool, PrintBucket, PrintPrinter, PrintRequest
from apps.printing.permissions import CanManagePrinting, IsActiveRequester
from apps.printing.serializers import (
    ErrorSerializer,
    FilamentSpoolSerializer,
    PrintBucketSerializer,
    PrintPrinterSerializer,
    PrintRequestCreateSerializer,
    PrintRequestSerializer,
    PrintStartSerializer,
    RejectFailSerializer,
)
from apps.makerspaces.guards import require_module


ERROR_RESPONSES = {
    400: OpenApiResponse(ErrorSerializer, description="Invalid request."),
    401: OpenApiResponse(description="Authentication credentials were not provided."),
    403: OpenApiResponse(description="Permission denied."),
    404: OpenApiResponse(description="Not found."),
}
ACTION_RESPONSES = {
    **ERROR_RESPONSES,
    409: OpenApiResponse(ErrorSerializer, description="Invalid status transition."),
}


def _int_query_param(request, name, *, required=False):
    value = request.query_params.get(name)
    if value in (None, ""):
        if required:
            raise ValidationError({name: "This query parameter is required."})
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({name: "Must be an integer."}) from exc


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
                "bucket__makerspace", "requester", "handled_by"
            )
            .filter(requester=self.request.user)
            .order_by("-created_at")
        )

    @extend_schema(
        responses={200: PrintRequestSerializer(many=True), **ERROR_RESPONSES},
    )
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
                "bucket__makerspace", "requester", "handled_by"
            )
            .filter(requester=self.request.user)
            .order_by("-created_at")
        )

    @extend_schema(responses={200: PrintRequestSerializer, **ERROR_RESPONSES})
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


@extend_schema(tags=["Printing"], summary="List active print buckets")
class PrintBucketListView(generics.ListAPIView):
    permission_classes = [IsActiveRequester]
    serializer_class = PrintBucketSerializer
    pagination_class = None

    def get_queryset(self):
        makerspace_id = _int_query_param(self.request, "makerspace", required=True)
        require_module(makerspace_id, "printing")
        return PrintBucket.objects.filter(
            makerspace_id=makerspace_id,
            is_active=True,
        ).order_by("name")

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="makerspace",
                type=int,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Makerspace id whose active buckets should be listed.",
            ),
        ],
        responses={200: PrintBucketSerializer(many=True), **ERROR_RESPONSES},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ManagedPrintRequestQuerysetMixin:
    def get_queryset(self):
        qs = PrintRequest.objects.select_related(
            "bucket__makerspace", "requester", "handled_by"
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

        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        bucket_id = _int_query_param(self.request, "bucket")
        if bucket_id is not None:
            qs = qs.filter(bucket_id=bucket_id)

        return qs


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
        return self.scope_queryset(
            PrintPrinter.objects.prefetch_related("filament_spools", "print_requests")
        )

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


@extend_schema(tags=["Printing"], summary="Retrieve or update managed 3D printer")
class ManagedPrinterDetailView(ManagedPrinterMixin, generics.RetrieveUpdateAPIView):
    serializer_class = PrintPrinterSerializer

    def get_queryset(self):
        return self.scope_queryset(
            PrintPrinter.objects.prefetch_related("filament_spools", "print_requests")
        )

    def perform_update(self, serializer):
        makerspace_id = serializer.validated_data.get(
            "makerspace_id", serializer.instance.makerspace_id
        )
        self.assert_can_manage_makerspace(makerspace_id)
        serializer.save()

    @extend_schema(responses={200: PrintPrinterSerializer, **ERROR_RESPONSES})
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        request=PrintPrinterSerializer,
        responses={200: PrintPrinterSerializer, **ERROR_RESPONSES},
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)


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
class ManagedFilamentSpoolDetailView(ManagedPrinterMixin, generics.RetrieveUpdateAPIView):
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

    @extend_schema(responses={200: FilamentSpoolSerializer, **ERROR_RESPONSES})
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        request=FilamentSpoolSerializer,
        responses={200: FilamentSpoolSerializer, **ERROR_RESPONSES},
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)


@extend_schema(tags=["Printing"], summary="List managed print requests")
class ManagedPrintRequestListView(
    ManagedPrintRequestQuerysetMixin, generics.ListAPIView
):
    permission_classes = [CanManagePrinting]
    serializer_class = PrintRequestSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter("makerspace", int, OpenApiParameter.QUERY),
            OpenApiParameter("status", str, OpenApiParameter.QUERY),
            OpenApiParameter("bucket", int, OpenApiParameter.QUERY),
        ],
        responses={200: PrintRequestSerializer(many=True), **ERROR_RESPONSES},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


@extend_schema(tags=["Printing"], summary="Retrieve managed print request")
class ManagedPrintRequestDetailView(
    ManagedPrintRequestQuerysetMixin, generics.RetrieveAPIView
):
    permission_classes = [CanManagePrinting]
    serializer_class = PrintRequestSerializer

    @extend_schema(responses={200: PrintRequestSerializer, **ERROR_RESPONSES})
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


@extend_schema(tags=["Printing"], summary="List completed print requests")
class PrintedListView(ManagedPrintRequestQuerysetMixin, generics.ListAPIView):
    permission_classes = [CanManagePrinting]
    serializer_class = PrintRequestSerializer

    def get_queryset(self):
        return super().get_queryset().filter(status=PrintRequest.Status.COMPLETED)

    @extend_schema(
        parameters=[
            OpenApiParameter("makerspace", int, OpenApiParameter.QUERY),
            OpenApiParameter("bucket", int, OpenApiParameter.QUERY),
        ],
        responses={200: PrintRequestSerializer(many=True), **ERROR_RESPONSES},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class PrintRequestActionView(ManagedPrintRequestQuerysetMixin, generics.GenericAPIView):
    permission_classes = [CanManagePrinting]
    serializer_class = PrintRequestSerializer
    action = None
    request_serializer_class = None

    def post(self, request, *args, **kwargs):
        print_request = self.get_object()
        require_module(print_request.bucket.makerspace, "printing")
        input_serializer = None
        if self.request_serializer_class is not None:
            input_serializer = self.request_serializer_class(data=request.data)
            input_serializer.is_valid(raise_exception=True)

        try:
            if self.action == "accept":
                updated = workflow.accept(print_request, request.user)
            elif self.action == "reject":
                updated = workflow.reject(
                    print_request,
                    request.user,
                    input_serializer.validated_data["reason"],
                )
            elif self.action == "start":
                input_data = input_serializer.validated_data if input_serializer else {}
                updated = workflow.start(
                    print_request,
                    request.user,
                    printer_id=input_data.get("printer_id"),
                    filament_spool_id=input_data.get("filament_spool_id"),
                    estimated_minutes=input_data.get("estimated_minutes"),
                    estimated_filament_grams=input_data.get("estimated_filament_grams"),
                )
            elif self.action == "complete":
                updated = workflow.complete(print_request, request.user)
            elif self.action == "fail":
                updated = workflow.fail(
                    print_request,
                    request.user,
                    input_serializer.validated_data["reason"],
                )
            else:
                raise AssertionError("Unknown print action.")
        except workflow.InvalidTransition as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(
            PrintRequestSerializer(updated, context=self.get_serializer_context()).data
        )


@extend_schema(tags=["Printing"], summary="Accept print request")
class PrintRequestAcceptView(PrintRequestActionView):
    action = "accept"

    @extend_schema(request=None, responses={200: PrintRequestSerializer, **ACTION_RESPONSES})
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


@extend_schema(tags=["Printing"], summary="Reject print request")
class PrintRequestRejectView(PrintRequestActionView):
    action = "reject"
    request_serializer_class = RejectFailSerializer

    @extend_schema(
        request=RejectFailSerializer,
        responses={200: PrintRequestSerializer, **ACTION_RESPONSES},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


@extend_schema(tags=["Printing"], summary="Start print request")
class PrintRequestStartView(PrintRequestActionView):
    action = "start"
    request_serializer_class = PrintStartSerializer

    @extend_schema(
        request=PrintStartSerializer,
        responses={200: PrintRequestSerializer, **ACTION_RESPONSES},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


@extend_schema(tags=["Printing"], summary="Complete print request")
class PrintRequestCompleteView(PrintRequestActionView):
    action = "complete"

    @extend_schema(request=None, responses={200: PrintRequestSerializer, **ACTION_RESPONSES})
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


@extend_schema(tags=["Printing"], summary="Mark print request failed")
class PrintRequestFailView(PrintRequestActionView):
    action = "fail"
    request_serializer_class = RejectFailSerializer

    @extend_schema(
        request=RejectFailSerializer,
        responses={200: PrintRequestSerializer, **ACTION_RESPONSES},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
