from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.hardware_requests.exceptions import ErrorSerializer
from apps.makerspaces.member_activity_service import active_membership
from apps.payments.models import Payment
from apps.payments.serializers import MemberPaymentSerializer
from apps.payments.serializers import CheckoutUrlSerializer
from apps.payments.services import create_checkout_url


class MemberPaymentHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Payments"], summary="List the caller's payment history", request=None, responses={200: MemberPaymentSerializer(many=True), 403: OpenApiResponse(ErrorSerializer)})
    def get(self, request, makerspace_id):
        if active_membership(request.user, makerspace_id) is None:
            return Response({"detail": "An active membership is required."}, status=403)
        rows = Payment.objects.filter(makerspace_id=makerspace_id, member=request.user).order_by("-created_at")
        return Response(MemberPaymentSerializer(rows, many=True).data)


class MemberPaymentCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Payments"],
        summary="Generate a Checkout link for the caller's pending payment",
        request=None,
        responses={200: CheckoutUrlSerializer, 404: OpenApiResponse(ErrorSerializer), 503: OpenApiResponse(ErrorSerializer)},
    )
    def post(self, request, makerspace_id, payment_id):
        payment = Payment.objects.filter(
            pk=payment_id,
            makerspace_id=makerspace_id,
            member=request.user,
            status=Payment.Status.PENDING,
        ).first()
        if payment is None:
            raise NotFound()
        if payment.stripe_checkout_url:
            return Response({"checkout_url": payment.stripe_checkout_url})
        try:
            checkout_url = create_checkout_url(payment.pk)
        except Exception:
            return Response({"detail": "Payments are temporarily unavailable.", "code": "payments_unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if not checkout_url:
            raise NotFound()
        return Response({"checkout_url": checkout_url})
