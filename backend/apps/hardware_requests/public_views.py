from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.checkin import client as checkin
from apps.hardware_requests import workflow
from apps.hardware_requests.serializers import (
    CheckinVerifyRequestSerializer,
    CheckinVerifyResponseSerializer,
    PublicRequestListItemSerializer,
    PublicRequestLookupSerializer,
    PublicRequestStatusSerializer,
    RequestSubmitResponseSerializer,
    RequestSubmitSerializer,
)
from apps.hardware_requests.view_helpers import (
    ERROR_404,
    PUBLIC_ERROR_RESPONSES,
    request_queryset,
)
from apps.inventory.models import InventoryProduct
from apps.makerspaces.lookup import get_public_makerspace
from apps.makerspaces.platform import module_enabled
from apps.openapi import (
    PUBLIC_REQUEST_LOOKUP_EXAMPLE,
    PUBLIC_REQUEST_STATUS_EXAMPLE,
    PUBLIC_REQUEST_SUBMIT_EXAMPLE,
    PUBLISHABLE_KEY_PARAMETER,
)


class CheckinVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "checkin_verify"

    @extend_schema(
        tags=["Public requests"],
        summary="Verify Check-In email or phone",
        auth=[],
        parameters=[PUBLISHABLE_KEY_PARAMETER],
        request=CheckinVerifyRequestSerializer,
        responses={200: CheckinVerifyResponseSerializer, **PUBLIC_ERROR_RESPONSES},
        examples=[PUBLIC_REQUEST_LOOKUP_EXAMPLE],
    )
    def post(self, request, makerspace_slug, *args, **kwargs):
        makerspace = get_public_makerspace(makerspace_slug)
        _require_module(makerspace, "request_workflow")
        serializer = CheckinVerifyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = checkin.verify(makerspace, serializer.validated_data["identifier"])
        return Response(CheckinVerifyResponseSerializer(result).data)


class RequestSubmitView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "request_submit"

    @extend_schema(
        tags=["Public requests"],
        summary="Submit public borrow request",
        auth=[],
        parameters=[PUBLISHABLE_KEY_PARAMETER],
        request=RequestSubmitSerializer,
        responses={201: RequestSubmitResponseSerializer, **PUBLIC_ERROR_RESPONSES},
        examples=[PUBLIC_REQUEST_SUBMIT_EXAMPLE],
    )
    def post(self, request, makerspace_slug, *args, **kwargs):
        makerspace = get_public_makerspace(makerspace_slug)
        _require_module(makerspace, "request_workflow")
        serializer = RequestSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        product_ids = [item["product_id"] for item in data["items"]]
        products = _requestable_products(product_ids, makerspace)
        if len(products) != len(product_ids):
            raise ValidationError(
                {"items": "One or more products are unavailable for request."}
            )

        hardware_request = workflow.submit_request(
            makerspace,
            data["identifier"],
            [
                {
                    "product": products[item["product_id"]],
                    "quantity": item["quantity"],
                }
                for item in data["items"]
            ],
            data["requested_for"],
            contact_email=data["contact_email"],
            contact_phone=data["contact_phone"],
        )
        return Response(
            RequestSubmitResponseSerializer(hardware_request).data,
            status=status.HTTP_201_CREATED,
        )


class RequestStatusView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "request_status"
    serializer_class = PublicRequestStatusSerializer
    lookup_field = "public_token"

    def get_queryset(self):
        from apps.hardware_requests.view_helpers import request_queryset

        return request_queryset()

    @extend_schema(
        tags=["Public requests"],
        summary="Get request status by public token",
        auth=[],
        parameters=[PUBLISHABLE_KEY_PARAMETER],
        responses={200: PublicRequestStatusSerializer, 404: ERROR_404},
        examples=[PUBLIC_REQUEST_STATUS_EXAMPLE],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class RequestLookupView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "request_status"

    @extend_schema(
        tags=["Public requests"],
        summary="List request statuses by Check-In email or phone",
        auth=[],
        parameters=[PUBLISHABLE_KEY_PARAMETER],
        request=PublicRequestLookupSerializer,
        responses={200: PublicRequestListItemSerializer(many=True), **PUBLIC_ERROR_RESPONSES},
        examples=[PUBLIC_REQUEST_LOOKUP_EXAMPLE, PUBLIC_REQUEST_STATUS_EXAMPLE],
    )
    def post(self, request, makerspace_slug, *args, **kwargs):
        makerspace = get_public_makerspace(makerspace_slug)
        _require_module(makerspace, "request_workflow")
        serializer = PublicRequestLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        identifier = serializer.validated_data["identifier"].strip()

        # Verify ownership through Check-In before disclosing any history. Matching
        # free-text contact fields let anyone who knew a requester's email/phone
        # enumerate their requests (incl. public_token). Instead we verify the
        # identifier and scope to the resolved Check-In identity. A denied/unknown
        # identifier raises through the workflow exception handler (403/503).
        result = checkin.verify(makerspace, identifier)
        queryset = (
            request_queryset()
            .filter(
                makerspace=makerspace,
                requester__external_checkin_user_id=result.external_id,
            )
            .order_by("-created_at")
        )
        return Response(PublicRequestListItemSerializer(queryset, many=True).data)


def _requestable_products(product_ids, makerspace):
    return {
        product.pk: product
        for product in InventoryProduct.objects.filter(
            pk__in=product_ids,
            makerspace=makerspace,
            is_public=True,
            is_archived=False,
        )
    }


def _require_module(makerspace, module_key):
    if not module_enabled(makerspace, module_key):
        raise ValidationError({"module": f"{module_key} is disabled for this makerspace."})
