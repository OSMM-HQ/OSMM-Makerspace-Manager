"""Staff queue endpoints for generic machine service requests."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.accounts.models import User
from apps.admin_api.permissions import IsActiveStaff
from apps.admin_api.serializers_machine_service import (
    EmptyServiceActionSerializer, MachineServiceRequestSerializer,
    MachineServiceSubmitSerializer, ServiceAcceptSerializer, ServiceCompleteSerializer,
    ServiceFailSerializer, ServiceRejectSerializer, ServiceStartSerializer,
)
from apps.hardware_requests.exceptions import ErrorSerializer
from apps.machines import service_workflow
from apps.machines.models import Machine, MachineServiceRequest
from apps.makerspaces.guards import require_module
from apps.makerspaces.models import Makerspace, MakerspaceMembership


SERVICE_ERRORS = {
    400: OpenApiResponse(ErrorSerializer, description="Invalid service request input."),
    401: OpenApiResponse(description="Authentication required."),
    403: OpenApiResponse(description="Machine management permission required."),
    404: OpenApiResponse(description="Service request was not found."),
    409: OpenApiResponse(ErrorSerializer, description="Service workflow conflict."),
}
SERVICE_FILTERS = [
    OpenApiParameter("status", str, OpenApiParameter.QUERY),
    OpenApiParameter("machine", int, OpenApiParameter.QUERY),
    OpenApiParameter("bucket", int, OpenApiParameter.QUERY),
]


def _visible_makerspace(actor, makerspace_id):
    makerspace = get_object_or_404(
        rbac.scope_by_makerspace(actor, Makerspace.objects.all(), makerspace_field="id"),
        pk=makerspace_id,
    )
    require_module(makerspace, "machine_service")
    if not rbac.can(actor, rbac.Action.MANAGE_MACHINES, makerspace.pk):
        raise PermissionDenied()
    return makerspace


def _request_queryset(actor):
    queryset = MachineServiceRequest.objects.select_related(
        "bucket__machine", "assigned_machine", "requester"
    ).prefetch_related("files", "consumptions")
    return rbac.scope_by_action(actor, rbac.Action.MANAGE_MACHINES, queryset,
                                field="bucket__machine__makerspace_id")


def _manageable_request(actor, pk):
    # Tenant visibility is established before the action check, so foreign/hidden
    # rows remain a 404 while an in-space but unauthorized actor receives a 403.
    row = get_object_or_404(
        rbac.scope_by_makerspace(
            actor,
            MachineServiceRequest.objects.select_related(
                "bucket__machine__makerspace", "assigned_machine", "requester"
            ).prefetch_related("files", "consumptions"),
            makerspace_field="bucket__machine__makerspace_id",
        ), pk=pk,
    )
    require_module(row.bucket.machine.makerspace, "machine_service")
    if not rbac.can(actor, rbac.Action.MANAGE_MACHINES, row.bucket.machine.makerspace_id):
        raise PermissionDenied()
    return get_object_or_404(_request_queryset(actor), pk=row.pk)


def _query_int(request, name):
    value = request.query_params.get(name)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({name: "Must be an integer."}) from exc


def _response(row, code=status.HTTP_200_OK):
    row = MachineServiceRequest.objects.select_related(
        "bucket__machine", "assigned_machine", "requester"
    ).prefetch_related("files", "consumptions").get(pk=row.pk)
    return Response(MachineServiceRequestSerializer(row).data, status=code)


class MachineServiceRequestListCreateView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(tags=["Admin machine service"], summary="List machine service requests",
                   parameters=SERVICE_FILTERS,
                   responses={200: MachineServiceRequestSerializer(many=True), **SERVICE_ERRORS})
    def get(self, request, makerspace_id, *args, **kwargs):
        makerspace = _visible_makerspace(request.user, makerspace_id)
        rows = _request_queryset(request.user).filter(bucket__machine__makerspace=makerspace)
        status_value = request.query_params.get("status")
        if status_value not in (None, ""):
            rows = rows.filter(status=status_value)
        for name, field in (("machine", "bucket__machine_id"), ("bucket", "bucket_id")):
            if value := _query_int(request, name):
                rows = rows.filter(**{field: value})
        return Response(MachineServiceRequestSerializer(rows.order_by("-created_at"), many=True).data)

    @extend_schema(tags=["Admin machine service"], summary="Submit a machine service request for a member",
                   request=MachineServiceSubmitSerializer,
                   responses={201: MachineServiceRequestSerializer, **SERVICE_ERRORS})
    def post(self, request, makerspace_id, *args, **kwargs):
        makerspace = _visible_makerspace(request.user, makerspace_id)
        serializer = MachineServiceSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        member = get_object_or_404(
            MakerspaceMembership.objects.select_related("user").filter(
                makerspace=makerspace, user_id=data["requester_id"], user__is_active=True
            )
        )
        machine = get_object_or_404(Machine.objects.filter(makerspace=makerspace), pk=data["machine_id"])
        requester = member.user
        row = service_workflow.submit(
            machine, requester, actor=request.user,
            member=requester,
            requester_name=data.get("requester_name") or requester.get_full_name().strip() or requester.username,
            contact_email=data.get("contact_email") or requester.email,
            contact_phone=data.get("contact_phone") or requester.phone,
            title=data["title"], description=data.get("description", ""),
            source_link=data.get("source_link", ""),
        )
        return _response(row, status.HTTP_201_CREATED)


class MachineServiceRequestDetailView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(tags=["Admin machine service"], summary="Retrieve a machine service request",
                   responses={200: MachineServiceRequestSerializer, **SERVICE_ERRORS})
    def get(self, request, pk, *args, **kwargs):
        return _response(_manageable_request(request.user, pk))


class _MachineServiceActionView(APIView):
    permission_classes = [IsActiveStaff]
    input_serializer = EmptyServiceActionSerializer
    operation = None

    def post(self, request, pk, *args, **kwargs):
        row = _manageable_request(request.user, pk)
        serializer = self.input_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if self.operation == "accept":
            row = service_workflow.accept(row, request.user, **data)
        elif self.operation == "reject":
            row = service_workflow.reject(row, request.user, **data)
        elif self.operation == "start":
            row = service_workflow.start(row, request.user, **data)
        elif self.operation == "complete":
            row = service_workflow.complete(row, request.user, **data)
        elif self.operation == "fail":
            row = service_workflow.fail(row, request.user, **data)
        elif self.operation == "collect":
            row = service_workflow.collect(row, request.user)
        else:
            raise AssertionError("Unknown service action")
        return _response(row)


class MachineServiceAcceptView(_MachineServiceActionView):
    input_serializer, operation = ServiceAcceptSerializer, "accept"

    @extend_schema(tags=["Admin machine service"], summary="Accept a machine service request",
                   request=ServiceAcceptSerializer, responses={200: MachineServiceRequestSerializer, **SERVICE_ERRORS})
    def post(self, request, pk, *args, **kwargs): return super().post(request, pk, *args, **kwargs)


class MachineServiceRejectView(_MachineServiceActionView):
    input_serializer, operation = ServiceRejectSerializer, "reject"

    @extend_schema(tags=["Admin machine service"], summary="Reject a machine service request",
                   request=ServiceRejectSerializer, responses={200: MachineServiceRequestSerializer, **SERVICE_ERRORS})
    def post(self, request, pk, *args, **kwargs): return super().post(request, pk, *args, **kwargs)


class MachineServiceStartView(_MachineServiceActionView):
    input_serializer, operation = ServiceStartSerializer, "start"

    @extend_schema(tags=["Admin machine service"], summary="Start machine service work",
                   request=ServiceStartSerializer, responses={200: MachineServiceRequestSerializer, **SERVICE_ERRORS})
    def post(self, request, pk, *args, **kwargs): return super().post(request, pk, *args, **kwargs)


class MachineServiceCompleteView(_MachineServiceActionView):
    input_serializer, operation = ServiceCompleteSerializer, "complete"

    @extend_schema(tags=["Admin machine service"], summary="Complete machine service work",
                   request=ServiceCompleteSerializer, responses={200: MachineServiceRequestSerializer, **SERVICE_ERRORS})
    def post(self, request, pk, *args, **kwargs): return super().post(request, pk, *args, **kwargs)


class MachineServiceFailView(_MachineServiceActionView):
    input_serializer, operation = ServiceFailSerializer, "fail"

    @extend_schema(tags=["Admin machine service"], summary="Mark machine service work failed",
                   request=ServiceFailSerializer, responses={200: MachineServiceRequestSerializer, **SERVICE_ERRORS})
    def post(self, request, pk, *args, **kwargs): return super().post(request, pk, *args, **kwargs)


class MachineServiceCollectView(_MachineServiceActionView):
    operation = "collect"

    @extend_schema(tags=["Admin machine service"], summary="Mark a machine service request collected",
                   request=EmptyServiceActionSerializer, responses={200: MachineServiceRequestSerializer, **SERVICE_ERRORS})
    def post(self, request, pk, *args, **kwargs): return super().post(request, pk, *args, **kwargs)
