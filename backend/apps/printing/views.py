from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts import rbac
from apps.printing import workflow
from apps.printing.models import PrintBucket, PrintRequest
from apps.printing.permissions import CanManagePrinting, IsActiveRequester
from apps.printing.serializers import (
    ErrorSerializer,
    PrintBucketSerializer,
    PrintRequestCreateSerializer,
    PrintRequestSerializer,
    RejectFailSerializer,
)


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
        instance = serializer.save()
        return Response(
            PrintRequestSerializer(instance, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


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


class PrintBucketListView(generics.ListAPIView):
    permission_classes = [IsActiveRequester]
    serializer_class = PrintBucketSerializer
    pagination_class = None

    def get_queryset(self):
        makerspace_id = _int_query_param(self.request, "makerspace", required=True)
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
            qs = qs.filter(bucket__makerspace_id=makerspace_id)

        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        bucket_id = _int_query_param(self.request, "bucket")
        if bucket_id is not None:
            qs = qs.filter(bucket_id=bucket_id)

        return qs


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


class ManagedPrintRequestDetailView(
    ManagedPrintRequestQuerysetMixin, generics.RetrieveAPIView
):
    permission_classes = [CanManagePrinting]
    serializer_class = PrintRequestSerializer

    @extend_schema(responses={200: PrintRequestSerializer, **ERROR_RESPONSES})
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


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
                updated = workflow.start(print_request, request.user)
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


class PrintRequestAcceptView(PrintRequestActionView):
    action = "accept"

    @extend_schema(request=None, responses={200: PrintRequestSerializer, **ACTION_RESPONSES})
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class PrintRequestRejectView(PrintRequestActionView):
    action = "reject"
    request_serializer_class = RejectFailSerializer

    @extend_schema(
        request=RejectFailSerializer,
        responses={200: PrintRequestSerializer, **ACTION_RESPONSES},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class PrintRequestStartView(PrintRequestActionView):
    action = "start"

    @extend_schema(request=None, responses={200: PrintRequestSerializer, **ACTION_RESPONSES})
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class PrintRequestCompleteView(PrintRequestActionView):
    action = "complete"

    @extend_schema(request=None, responses={200: PrintRequestSerializer, **ACTION_RESPONSES})
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class PrintRequestFailView(PrintRequestActionView):
    action = "fail"
    request_serializer_class = RejectFailSerializer

    @extend_schema(
        request=RejectFailSerializer,
        responses={200: PrintRequestSerializer, **ACTION_RESPONSES},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
