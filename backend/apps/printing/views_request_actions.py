from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.makerspaces.guards import require_module
from apps.printing import workflow
from apps.printing.permissions import CanManagePrinting
from apps.printing.serializers import (
    CompletePrintSerializer,
    FailPrintSerializer,
    ManagedPrintRequestSerializer,
    PrintAcceptSerializer,
    PrintStartSerializer,
    RejectFailSerializer,
)
from apps.printing.views_common import ACTION_RESPONSES
from apps.printing.views_requests import ManagedPrintRequestQuerysetMixin


class PrintRequestActionView(ManagedPrintRequestQuerysetMixin, generics.GenericAPIView):
    permission_classes = [CanManagePrinting]
    serializer_class = ManagedPrintRequestSerializer
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
                updated = workflow.accept(
                    print_request,
                    request.user,
                    price=input_serializer.validated_data["price"],
                )
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
                input_data = input_serializer.validated_data if input_serializer else {}
                updated = workflow.complete(
                    print_request,
                    request.user,
                    actual_filament_grams=input_data.get("actual_filament_grams"),
                )
            elif self.action == "fail":
                updated = workflow.fail(
                    print_request,
                    request.user,
                    input_serializer.validated_data["reason"],
                    percent_complete=input_serializer.validated_data.get(
                        "percent_complete",
                        0,
                    ),
                )
            elif self.action == "collect":
                updated = workflow.mark_collected(print_request, request.user)
            else:
                raise AssertionError("Unknown print action.")
        except workflow.InvalidTransition as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(
            ManagedPrintRequestSerializer(
                updated,
                context=self.get_serializer_context(),
            ).data
        )


@extend_schema(tags=["Printing"], summary="Accept print request")
class PrintRequestAcceptView(PrintRequestActionView):
    action = "accept"
    request_serializer_class = PrintAcceptSerializer

    @extend_schema(
        request=PrintAcceptSerializer,
        responses={200: ManagedPrintRequestSerializer, **ACTION_RESPONSES},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


@extend_schema(tags=["Printing"], summary="Reject print request")
class PrintRequestRejectView(PrintRequestActionView):
    action = "reject"
    request_serializer_class = RejectFailSerializer

    @extend_schema(
        request=RejectFailSerializer,
        responses={200: ManagedPrintRequestSerializer, **ACTION_RESPONSES},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


@extend_schema(tags=["Printing"], summary="Start print request")
class PrintRequestStartView(PrintRequestActionView):
    action = "start"
    request_serializer_class = PrintStartSerializer

    @extend_schema(
        request=PrintStartSerializer,
        responses={200: ManagedPrintRequestSerializer, **ACTION_RESPONSES},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


@extend_schema(tags=["Printing"], summary="Complete print request")
class PrintRequestCompleteView(PrintRequestActionView):
    action = "complete"
    request_serializer_class = CompletePrintSerializer

    @extend_schema(
        request=CompletePrintSerializer,
        responses={200: ManagedPrintRequestSerializer, **ACTION_RESPONSES},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


@extend_schema(tags=["Printing"], summary="Mark print request failed")
class PrintRequestFailView(PrintRequestActionView):
    action = "fail"
    request_serializer_class = FailPrintSerializer

    @extend_schema(
        request=FailPrintSerializer,
        responses={200: ManagedPrintRequestSerializer, **ACTION_RESPONSES},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


@extend_schema(tags=["Printing"], summary="Collect print request")
class PrintRequestCollectView(PrintRequestActionView):
    action = "collect"

    @extend_schema(
        request=None,
        responses={200: ManagedPrintRequestSerializer, **ACTION_RESPONSES},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


@extend_schema(
    tags=["Printing"],
    summary="Reprint a failed print request",
    request=None,
    responses={201: ManagedPrintRequestSerializer, **ACTION_RESPONSES},
)
class PrintRequestReprintView(
    ManagedPrintRequestQuerysetMixin,
    generics.GenericAPIView,
):
    permission_classes = [CanManagePrinting]
    serializer_class = ManagedPrintRequestSerializer

    def post(self, request, *args, **kwargs):
        print_request = self.get_object()
        require_module(print_request.bucket.makerspace, "printing")
        try:
            updated = workflow.reprint(print_request, request.user)
        except workflow.InvalidTransition as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(
            ManagedPrintRequestSerializer(
                updated,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_201_CREATED,
        )
