from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.accounts.models import User
from apps.hardware_requests import direct_loan_workflow
from apps.hardware_requests.direct_loan_serializers import (
    DirectLoanIssueSerializer,
    DirectLoanReturnSerializer,
    DirectLoanSerializer,
)
from apps.hardware_requests.models import PublicToolLoan
from apps.hardware_requests.view_helpers import ACTION_ERROR_RESPONSES
from apps.makerspaces.models import Makerspace
from apps.makerspaces.guards import require_module


class DirectLoanListCreateView(generics.ListAPIView):
    serializer_class = DirectLoanSerializer

    def get_queryset(self):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(makerspace_id, "self_checkout")
        _require(self.request.user, rbac.Action.ISSUE_DIRECT_LOAN, makerspace_id)
        queryset = PublicToolLoan.objects.select_related("request", "requester").filter(
            makerspace_id=makerspace_id,
            source=PublicToolLoan.Source.ADMIN_DIRECT,
        )
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset.order_by("-checked_out_at")

    @extend_schema(
        tags=["Admin requests"],
        summary="List direct handout loans",
        responses={200: DirectLoanSerializer(many=True), **ACTION_ERROR_RESPONSES},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        tags=["Admin requests"],
        summary="Issue direct handout without public request",
        request=DirectLoanIssueSerializer,
        responses={201: DirectLoanSerializer, **ACTION_ERROR_RESPONSES},
    )
    def post(self, request, makerspace_id, *args, **kwargs):
        makerspace = get_object_or_404(Makerspace, pk=makerspace_id)
        require_module(makerspace, "self_checkout")
        _require(request.user, rbac.Action.ISSUE_DIRECT_LOAN, makerspace.id)
        serializer = DirectLoanIssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        loan = direct_loan_workflow.issue_direct_loan(
            makerspace,
            request.user,
            serializer.validated_data["identifier"],
            qr_payloads=serializer.validated_data.get("qr_payloads") or [],
            items=serializer.validated_data.get("items") or [],
            due_at=serializer.validated_data.get("due_at"),
        )
        return Response(DirectLoanSerializer(loan).data, status=status.HTTP_201_CREATED)


class DirectLoanReturnView(APIView):
    @extend_schema(
        tags=["Admin requests"],
        summary="Return direct handout loan",
        request=DirectLoanReturnSerializer,
        responses={200: DirectLoanSerializer, **ACTION_ERROR_RESPONSES},
    )
    def post(self, request, pk, *args, **kwargs):
        # Only admin_direct loans use this path; a public self-checkout loan must
        # go through the QR/requester return flow, not the admin direct-return.
        loan = get_object_or_404(
            PublicToolLoan, pk=pk, source=PublicToolLoan.Source.ADMIN_DIRECT
        )
        require_module(loan.makerspace, "self_checkout")
        _require(request.user, rbac.Action.RETURN_REQUEST, loan.makerspace_id)
        returned = direct_loan_workflow.return_direct_loan(loan, request.user)
        return Response(DirectLoanSerializer(returned).data)


def _require(user, action, makerspace_id):
    # rbac.can() only checks membership/action, not account standing. Mirror the
    # active-status gate the IsStaff/HasMakerspaceAction permissions enforce so a
    # suspended user with an unexpired JWT can't keep issuing/returning loans.
    if getattr(user, "access_status", None) != User.AccessStatus.ACTIVE:
        raise PermissionDenied()
    if not rbac.can(user, action, makerspace_id):
        raise PermissionDenied()
