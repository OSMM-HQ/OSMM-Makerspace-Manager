from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.hardware_requests import workflow
from apps.hardware_requests.permissions import CanReviewRequest
from apps.hardware_requests.serializers import (
    AdminRequestSerializer,
    RejectRequestSerializer,
)
from apps.hardware_requests.view_helpers import (
    ACTION_ERROR_RESPONSES,
    request_queryset,
)
from apps.makerspaces.guards import require_module


class AcceptRequestView(APIView):
    permission_classes = [CanReviewRequest]

    @extend_schema(
        tags=["Admin requests"],
        summary="Accept borrow request",
        request=None,
        responses={200: AdminRequestSerializer, **ACTION_ERROR_RESPONSES},
    )
    def post(self, request, pk, *args, **kwargs):
        hardware_request = _scoped_request(request.user, pk)
        if not rbac.can(
            request.user,
            rbac.Action.ACCEPT_REQUEST,
            hardware_request.makerspace_id,
        ):
            raise PermissionDenied()

        updated = workflow.accept_request(request.user, hardware_request)
        return Response(AdminRequestSerializer(updated).data)


class RejectRequestView(APIView):
    permission_classes = [CanReviewRequest]

    @extend_schema(
        tags=["Admin requests"],
        summary="Reject borrow request",
        request=RejectRequestSerializer,
        responses={200: AdminRequestSerializer, **ACTION_ERROR_RESPONSES},
    )
    def post(self, request, pk, *args, **kwargs):
        hardware_request = _scoped_request(request.user, pk)
        if not rbac.can(
            request.user,
            rbac.Action.REJECT_REQUEST,
            hardware_request.makerspace_id,
        ):
            raise PermissionDenied()

        serializer = RejectRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = workflow.reject_request(
            request.user,
            hardware_request,
            serializer.validated_data["reason"],
        )
        return Response(AdminRequestSerializer(updated).data)


def _scoped_request(user, pk):
    scoped = rbac.scope_by_makerspace(user, request_queryset())
    hardware_request = get_object_or_404(scoped, pk=pk)
    require_module(hardware_request.makerspace, "request_workflow")
    return hardware_request
