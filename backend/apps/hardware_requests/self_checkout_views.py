from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.apiclients.throttling import ClientTierRateThrottle
from apps.hardware_requests import self_checkout_workflow
from apps.hardware_requests.self_checkout_serializers import (
    PublicToolCheckoutSerializer,
    PublicToolEvidenceUrlRequestSerializer,
    PublicToolLoanSerializer,
    PublicToolScanSerializer,
)
from apps.hardware_requests.view_helpers import PUBLIC_ERROR_RESPONSES
from apps.evidence.models import EvidencePhoto
from apps.evidence.responses import storage_unavailable_response
from apps.evidence.serializers import EvidenceUrlResponseSerializer
from apps.evidence.storage import StorageUnavailable, evidence_object_key, presigned_upload
from apps.checkin import client as checkin
from apps.hardware_requests.workflow_utils import get_or_create_requester
from apps.makerspaces.lookup import get_public_makerspace
from apps.makerspaces.platform import module_enabled
from apps.openapi import (
    PUBLIC_TOOL_CHECKOUT_EXAMPLE,
    PUBLIC_TOOL_SCAN_EXAMPLE,
    PUBLISHABLE_KEY_PARAMETER,
)
from rest_framework.exceptions import ValidationError


class PublicToolEvidenceUploadUrlView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ClientTierRateThrottle]
    throttle_scope = "public_tool_checkout"

    @extend_schema(
        tags=["Public requests"],
        summary="Create a public self-checkout evidence upload URL",
        auth=[],
        parameters=[PUBLISHABLE_KEY_PARAMETER],
        request=PublicToolEvidenceUrlRequestSerializer,
        responses={201: EvidenceUrlResponseSerializer, **PUBLIC_ERROR_RESPONSES},
    )
    def post(self, request, makerspace_slug, *args, **kwargs):
        makerspace = get_public_makerspace(makerspace_slug)
        _require_module(makerspace, "self_checkout")
        serializer = PublicToolEvidenceUrlRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["content_type"] not in settings.EVIDENCE_ALLOWED_MIME:
            raise ValidationError({"content_type": "Unsupported evidence content type."})
        result = checkin.verify(makerspace, data["identifier"])
        requester = get_or_create_requester(result.external_id)
        if requester.access_status != User.AccessStatus.ACTIVE:
            raise ValidationError({"identifier": "Requester is not active."})
        object_key = evidence_object_key(makerspace.id, data["evidence_type"])
        try:
            upload = presigned_upload(object_key, data["content_type"])
        except StorageUnavailable:
            return storage_unavailable_response()
        photo = EvidencePhoto.objects.create(
            makerspace=makerspace,
            evidence_type=data["evidence_type"],
            object_key=object_key,
            uploaded_by=requester,
        )
        response = {
            "evidence_id": photo.pk,
            "upload_url": upload["url"],
            "fields": upload.get("fields", {}),
            "object_key": object_key,
        }
        if upload.get("method"):
            response["method"] = upload["method"]
            response["headers"] = upload.get("headers", {})
        return Response(EvidenceUrlResponseSerializer(response).data, status=status.HTTP_201_CREATED)


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
            evidence_id=serializer.validated_data["evidence_id"],
            remark=serializer.validated_data.get("remark", ""),
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
            evidence_id=serializer.validated_data["evidence_id"],
            remark=serializer.validated_data["remark"],
        )
        return Response(PublicToolLoanSerializer(loan).data)


def _require_module(makerspace, module_key):
    if not module_enabled(makerspace, module_key):
        raise ValidationError({"module": f"{module_key} is disabled for this makerspace."})



