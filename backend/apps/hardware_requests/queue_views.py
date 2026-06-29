from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.filters import SearchFilter

from apps.accounts import rbac
from apps.hardware_requests.models import HardwareRequest
from apps.hardware_requests.permissions import CanReviewRequest, CanViewHandoverQueue
from apps.hardware_requests.serializers import AdminRequestSerializer
from apps.hardware_requests.view_helpers import (
    ADMIN_LIST_ERROR_RESPONSES,
    request_queryset,
)
from apps.makerspaces.models import Makerspace
from apps.makerspaces.guards import require_module

# Staff search the queues by who borrowed / what for. Scoped to the queue's own
# makerspace filter already, so this only narrows within the tenant.
REQUEST_SEARCH_FIELDS = [
    "requester_name",
    "requester_contact_email",
    "requester_contact_phone",
    "requested_for",
]


class PendingRequestsView(generics.ListAPIView):
    permission_classes = [CanReviewRequest]
    serializer_class = AdminRequestSerializer
    filter_backends = [SearchFilter]
    search_fields = REQUEST_SEARCH_FIELDS

    def get_queryset(self):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(makerspace_id, "request_workflow")
        _require_action(self.request.user, rbac.Action.ACCEPT_REQUEST, makerspace_id)
        return (
            request_queryset()
            .filter(
                makerspace_id=makerspace_id,
                status=HardwareRequest.Status.PENDING_APPROVAL,
            )
            .order_by("-created_at")
        )

    @extend_schema(
        tags=["Admin requests"],
        summary="List pending borrow requests",
        responses={200: AdminRequestSerializer(many=True), **ADMIN_LIST_ERROR_RESPONSES},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class AcceptedRequestsView(generics.ListAPIView):
    permission_classes = [CanViewHandoverQueue]
    serializer_class = AdminRequestSerializer
    filter_backends = [SearchFilter]
    search_fields = REQUEST_SEARCH_FIELDS

    def get_queryset(self):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(makerspace_id, "guest_handover")
        _require_action(self.request.user, rbac.Action.ISSUE_REQUEST, makerspace_id)
        return (
            request_queryset()
            .filter(
                makerspace_id=makerspace_id,
                status=HardwareRequest.Status.ACCEPTED,
            )
            .order_by("-created_at")
        )

    @extend_schema(
        tags=["Admin requests"],
        summary="List accepted requests awaiting issue",
        responses={200: AdminRequestSerializer(many=True), **ADMIN_LIST_ERROR_RESPONSES},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ActiveLoansView(generics.ListAPIView):
    permission_classes = [CanViewHandoverQueue]
    serializer_class = AdminRequestSerializer
    filter_backends = [SearchFilter]
    search_fields = REQUEST_SEARCH_FIELDS

    def get_queryset(self):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(makerspace_id, "guest_handover")
        _require_action(self.request.user, rbac.Action.ISSUE_REQUEST, makerspace_id)
        return (
            request_queryset()
            .filter(
                makerspace_id=makerspace_id,
                status__in=[
                    HardwareRequest.Status.ISSUED,
                    HardwareRequest.Status.PARTIALLY_RETURNED,
                ],
            )
            .order_by("-issued_at", "-created_at")
        )

    @extend_schema(
        tags=["Admin requests"],
        summary="List active loans awaiting return",
        responses={200: AdminRequestSerializer(many=True), **ADMIN_LIST_ERROR_RESPONSES},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class RequestHistoryView(generics.ListAPIView):
    # Terminal requests (returned / rejected / closed_with_issue) had no staff surface -
    # once a loan was returned or a request rejected it vanished from every queue, hiding
    # the accountability-bearing closed_with_issue loans (damaged/missing units). Gated on
    # ISSUE_REQUEST (the handover-queue viewers) to match the accepted/active loan views.
    permission_classes = [CanViewHandoverQueue]
    serializer_class = AdminRequestSerializer
    filter_backends = [SearchFilter]
    search_fields = REQUEST_SEARCH_FIELDS

    def get_queryset(self):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(makerspace_id, "guest_handover")
        _require_action(self.request.user, rbac.Action.ISSUE_REQUEST, makerspace_id)
        return (
            request_queryset()
            .filter(
                makerspace_id=makerspace_id,
                status__in=[
                    HardwareRequest.Status.RETURNED,
                    HardwareRequest.Status.REJECTED,
                    HardwareRequest.Status.CLOSED_WITH_ISSUE,
                ],
            )
            .order_by("-updated_at", "-created_at")
        )

    @extend_schema(
        tags=["Admin requests"],
        summary="List terminal request history (returned / rejected / closed with issue)",
        responses={200: AdminRequestSerializer(many=True), **ADMIN_LIST_ERROR_RESPONSES},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


def _require_action(user, action, makerspace_id):
    scoped = rbac.scope_by_action(user, action, Makerspace.objects.all(), field="id")
    get_object_or_404(scoped, pk=makerspace_id)
