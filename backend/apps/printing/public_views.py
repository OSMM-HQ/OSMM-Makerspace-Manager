"""Legacy public printing URLs delegated to the generic printer-service contract."""

import uuid
from types import SimpleNamespace

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.apiclients.throttling import ClientTierRateThrottle
from apps.machines.models import MachineServiceRequest
from apps.machines.public_printer_service import public_pools, public_queues, public_status, stage_upload, submit_request
from apps.makerspaces.lookup import get_public_makerspace
from apps.makerspaces.platform import module_enabled
from apps.presence.guard import require_active_member_presence
from apps.printing.permissions import IsActiveRequester
from apps.printing.public_serializers import (
    PrintPresignRequestSerializer, PrintPresignResponseSerializer,
    PrintRequestSubmitResponseSerializer, PrintRequestSubmitSerializer,
    PublicFilamentSpoolSerializer, PublicPrintBucketSerializer, PublicPrintStatusSerializer,
)
from apps.printing.serializers import ErrorSerializer
from apps.printing.storage import presigned_print_upload


PUBLIC_PRINT_ERROR_RESPONSES = {
    400: OpenApiResponse(ErrorSerializer, description="Invalid request."),
    401: OpenApiResponse(ErrorSerializer, description="Authentication is required."),
    403: OpenApiResponse(ErrorSerializer, description="Member presence is required."),
    404: OpenApiResponse(ErrorSerializer, description="Makerspace or request not found."),
    429: OpenApiResponse(ErrorSerializer, description="Request rate limit exceeded."),
    503: OpenApiResponse(ErrorSerializer, description="Storage is unavailable."),
}


def _require_module(makerspace):
    if not module_enabled(makerspace, "printing"):
        raise ValidationError({"module": "printing is disabled for this makerspace."})


def _honeypot_filled(payload):
    try:
        return bool(str(payload.get("website", "")).strip())
    except AttributeError:
        return False


def _canonical(data):
    """Translate retained bucket/spool names at the compatibility boundary."""
    return {
        **data,
        "queue_id": data.get("bucket_id"),
        "consumable_pool_id": data.get("filament_spool_id"),
    }


class PublicPrintBucketsView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ClientTierRateThrottle]
    throttle_scope = "public_read"

    @extend_schema(tags=["Public printing"], auth=[], responses={200: PublicPrintBucketSerializer(many=True), **PUBLIC_PRINT_ERROR_RESPONSES})
    def get(self, request, makerspace_slug):
        makerspace = get_public_makerspace(makerspace_slug)
        _require_module(makerspace)
        return Response(PublicPrintBucketSerializer(public_queues(makerspace), many=True).data)


class PublicPrintSpoolsView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ClientTierRateThrottle]
    throttle_scope = "public_read"

    @extend_schema(tags=["Public printing"], auth=[], responses={200: PublicFilamentSpoolSerializer(many=True), **PUBLIC_PRINT_ERROR_RESPONSES})
    def get(self, request, makerspace_slug):
        makerspace = get_public_makerspace(makerspace_slug)
        _require_module(makerspace)
        return Response(PublicFilamentSpoolSerializer(public_pools(makerspace), many=True).data)


class PrintUploadPresignView(APIView):
    permission_classes = [IsActiveRequester]
    throttle_classes = [ClientTierRateThrottle]
    throttle_scope = "print_request_submit"

    @extend_schema(tags=["Public printing"], request=PrintPresignRequestSerializer, responses={201: PrintPresignResponseSerializer, **PUBLIC_PRINT_ERROR_RESPONSES})
    def post(self, request, makerspace_slug):
        makerspace = get_public_makerspace(makerspace_slug)
        _require_module(makerspace)
        require_active_member_presence(request.user, makerspace)
        serializer = PrintPresignRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(stage_upload(makerspace, _canonical(serializer.validated_data), request.user, compatibility=True, legacy_presigner=presigned_print_upload), status=status.HTTP_201_CREATED)


class PrintRequestSubmitView(APIView):
    permission_classes = [IsActiveRequester]
    throttle_classes = [ClientTierRateThrottle]
    throttle_scope = "print_request_submit"

    @extend_schema(tags=["Public printing"], request=PrintRequestSubmitSerializer, responses={201: PrintRequestSubmitResponseSerializer, **PUBLIC_PRINT_ERROR_RESPONSES})
    def post(self, request, makerspace_slug):
        makerspace = get_public_makerspace(makerspace_slug)
        _require_module(makerspace)
        if _honeypot_filled(request.data):
            decoy = SimpleNamespace(public_token=uuid.uuid4(), status=MachineServiceRequest.Status.PENDING)
            return Response(PrintRequestSubmitResponseSerializer(decoy).data, status=status.HTTP_201_CREATED)
        require_active_member_presence(request.user, makerspace)
        serializer = PrintRequestSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = submit_request(makerspace, _canonical(serializer.validated_data), request.user, compatibility=True)
        return Response(PrintRequestSubmitResponseSerializer(row).data, status=status.HTTP_201_CREATED)


class PublicPrintStatusView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ClientTierRateThrottle]
    throttle_scope = "request_status"

    @extend_schema(tags=["Public printing"], auth=[], responses={200: PublicPrintStatusSerializer, **PUBLIC_PRINT_ERROR_RESPONSES})
    def get(self, request, public_token):
        row, counts = public_status(public_token)
        return Response(PublicPrintStatusSerializer(row, context={"queue_counts": counts}).data)