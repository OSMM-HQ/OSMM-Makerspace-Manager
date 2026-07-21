import logging

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.makerspaces.models import Makerspace
from apps.payments.models import MakerspacePaymentSettings
from apps.payments.stripe_client import (
    PaymentsUnavailable,
    StripeWebhookSignatureError,
    construct_event,
)

logger = logging.getLogger(__name__)


class StripeWebhookView(APIView):
    """Verify an incoming Stripe event and safely acknowledge it until C.3."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Payments"],
        summary="Verify a makerspace Stripe webhook",
        description=(
            "Verifies an event against the addressed makerspace's webhook secret. "
            "This foundation endpoint deliberately performs no payment state changes."
        ),
        auth=[],
        request=None,
        responses={
            200: OpenApiResponse(description="Verified event safely acknowledged."),
            400: OpenApiResponse(description="Invalid signature, payload, or configuration."),
            404: OpenApiResponse(description="Makerspace was not found or is archived."),
        },
    )
    def post(self, request, public_code):
        makerspace = Makerspace.objects.filter(
            public_code__iexact=public_code,
            archived_at__isnull=True,
        ).first()
        if makerspace is None:
            logger.warning("stripe_webhook_unknown_makerspace", extra={"public_code": public_code})
            return Response({"detail": "Makerspace not found."}, status=status.HTTP_404_NOT_FOUND)

        payment_settings = MakerspacePaymentSettings.for_makerspace(makerspace)
        if not payment_settings.is_configured:
            logger.warning("stripe_webhook_unconfigured", extra={"makerspace_id": makerspace.id})
            return Response({"detail": "Payments are not configured."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            webhook_secret = payment_settings.get_stripe_webhook_secret()
            event = construct_event(
                request.body,
                request.headers.get("Stripe-Signature", ""),
                webhook_secret,
            )
        except (StripeWebhookSignatureError, PaymentsUnavailable, ValueError):
            logger.warning("stripe_webhook_rejected", extra={"makerspace_id": makerspace.id})
            return Response({"detail": "Invalid Stripe webhook signature."}, status=status.HTTP_400_BAD_REQUEST)

        event_id = event.get("id") if isinstance(event, dict) else getattr(event, "id", None)
        event_type = event.get("type") if isinstance(event, dict) else getattr(event, "type", None)
        logger.info(
            "stripe_webhook_verified_unhandled",
            extra={
                "makerspace_id": makerspace.id,
                "event_id": event_id,
                "event_type": event_type,
            },
        )
        return Response({"detail": "Verified."}, status=status.HTTP_200_OK)
