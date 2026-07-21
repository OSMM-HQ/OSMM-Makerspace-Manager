from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff
from apps.hardware_requests.exceptions import ErrorSerializer
from apps.payments.models import Payment
from apps.payments.serializers import StaffPaymentSerializer
from apps.payments.services import mark_offline, waive


def _manageable_payment(actor, pk):
    payment = get_object_or_404(rbac.scope_by_action(actor, rbac.Action.MANAGE_MACHINES, Payment.objects.select_related("makerspace"), field="makerspace_id"), pk=pk)
    if payment.subject_type != Payment.SubjectType.MACHINE_SERVICE_REQUEST:
        raise PermissionDenied()
    return payment


class _PaymentActionView(APIView):
    permission_classes = [IsActiveStaff]
    operation = None

    def post(self, request, pk):
        payment = _manageable_payment(request.user, pk)
        payment = mark_offline(payment, request.user) if self.operation == "offline" else waive(payment, request.user)
        return Response(StaffPaymentSerializer(payment).data)


class PaymentMarkOfflineView(_PaymentActionView):
    operation = "offline"

    @extend_schema(tags=["Payments"], summary="Mark a machine-service payment paid offline", request=None, responses={200: StaffPaymentSerializer, 403: OpenApiResponse(ErrorSerializer), 404: OpenApiResponse(ErrorSerializer)})
    def post(self, request, pk):
        return super().post(request, pk)


class PaymentWaiveView(_PaymentActionView):
    operation = "waive"

    @extend_schema(tags=["Payments"], summary="Waive a machine-service payment", request=None, responses={200: StaffPaymentSerializer, 403: OpenApiResponse(ErrorSerializer), 404: OpenApiResponse(ErrorSerializer)})
    def post(self, request, pk):
        return super().post(request, pk)
