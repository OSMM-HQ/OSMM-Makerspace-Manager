from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.apiclients.throttling import ClientTierRateThrottle
from apps.hardware_requests import self_checkout_workflow
from apps.hardware_requests.self_checkout_serializers import (
    PublicToolCheckoutSerializer,
    PublicToolLoanSerializer,
    PublicToolScanSerializer,
)
from apps.hardware_requests.view_helpers import PUBLIC_ERROR_RESPONSES
from apps.makerspaces.lookup import get_public_makerspace
from apps.makerspaces.platform import module_enabled
from apps.openapi import (
    PUBLIC_TOOL_CHECKOUT_EXAMPLE,
    PUBLIC_TOOL_SCAN_EXAMPLE,
    PUBLISHABLE_KEY_PARAMETER,
)
from rest_framework.exceptions import ValidationError


class PublicToolCheckoutView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ClientTierRateThrottle]
    throttle_scope = "public_tool_checkout"

    @extend_schema(
        tags=["Public requests"],
        summary="Check out a public tool by QR",
        auth=[],
        parameters=[PUBLISHABLE_KEY_PARAMETER],
        request=PublicToolCheckoutSerializer,
        responses={201: PublicToolLoanSerializer, **PUBLIC_ERROR_RESPONSES},
        examples=[PUBLIC_TOOL_CHECKOUT_EXAMPLE],
    )
    def post(self, request, makerspace_slug, *args, **kwargs):
        makerspace = get_public_makerspace(makerspace_slug)
        _require_module(makerspace, "self_checkout")
        serializer = PublicToolCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        loan = self_checkout_workflow.checkout_tool(
            makerspace,
            serializer.validated_data["contact_email"],
            serializer.validated_data["payload"],
            requester_name=serializer.validated_data["requester_name"],
            contact_phone=serializer.validated_data["contact_phone"],
        )
        return Response(PublicToolLoanSerializer(loan).data, status=status.HTTP_201_CREATED)


class PublicToolReturnView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ClientTierRateThrottle]
    throttle_scope = "public_tool_return"

    @extend_schema(
        tags=["Public requests"],
        summary="Return a public tool by QR",
        auth=[],
        parameters=[PUBLISHABLE_KEY_PARAMETER],
        request=PublicToolScanSerializer,
        responses={200: PublicToolLoanSerializer, **PUBLIC_ERROR_RESPONSES},
        examples=[PUBLIC_TOOL_SCAN_EXAMPLE],
    )
    def post(self, request, makerspace_slug, *args, **kwargs):
        makerspace = get_public_makerspace(makerspace_slug)
        _require_module(makerspace, "self_checkout")
        serializer = PublicToolScanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        loan = self_checkout_workflow.return_tool(
            makerspace,
            serializer.validated_data["identifier"],
            serializer.validated_data["payload"],
        )
        return Response(PublicToolLoanSerializer(loan).data)


def _require_module(makerspace, module_key):
    if not module_enabled(makerspace, module_key):
        raise ValidationError({"module": f"{module_key} is disabled for this makerspace."})

