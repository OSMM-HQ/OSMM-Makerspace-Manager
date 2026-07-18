import uuid
from types import SimpleNamespace

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.apiclients.throttling import ClientTierRateThrottle
from apps.makerspaces.lookup import get_public_makerspace
from apps.makerspaces.platform import module_enabled
from apps.presence.guard import require_active_member_presence
from apps.printing import public_workflow
from apps.printing.models import FilamentSpool, PrintBucket, PrintRequest, PrintRequestFile
from apps.printing.permissions import IsActiveRequester
from apps.printing.public_serializers import (
    PrintPresignRequestSerializer,
    PrintPresignResponseSerializer,
    PrintRequestSubmitResponseSerializer,
    PrintRequestSubmitSerializer,
    PublicFilamentSpoolSerializer,
    PublicPrintBucketSerializer,
    PublicPrintStatusSerializer,
)
from apps.printing.queue_position import queue_counts_for
from apps.printing.serializers import ErrorSerializer
from apps.printing.storage import (
    presigned_print_upload,
    print_object_key,
    validate_print_upload,
)


def _require_module(makerspace):
    if not module_enabled(makerspace, "printing"):
        raise ValidationError({"module": "printing is disabled for this makerspace."})


def _honeypot_filled(payload):
    try:
        value = payload.get("website", "")
    except AttributeError:
        return False
    return bool(str(value).strip())


PUBLIC_PRINT_ERROR_RESPONSES = {
    400: OpenApiResponse(ErrorSerializer, description="Invalid request."),
    401: OpenApiResponse(ErrorSerializer, description="Authentication is required."),
    403: OpenApiResponse(ErrorSerializer, description="Member presence is required."),
    404: OpenApiResponse(ErrorSerializer, description="Makerspace or request not found."),
    429: OpenApiResponse(ErrorSerializer, description="Request rate limit exceeded."),
    503: OpenApiResponse(ErrorSerializer, description="Storage is unavailable."),
}


class PublicPrintBucketsView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ClientTierRateThrottle]
    throttle_scope = "public_read"

    @extend_schema(tags=["Public printing"], auth=[], responses={200: PublicPrintBucketSerializer(many=True), **PUBLIC_PRINT_ERROR_RESPONSES})
    def get(self, request, makerspace_slug):
        makerspace = get_public_makerspace(makerspace_slug)
        _require_module(makerspace)
        buckets = PrintBucket.objects.filter(makerspace=makerspace, is_active=True).order_by("name")
        return Response(PublicPrintBucketSerializer(buckets, many=True).data)


class PublicPrintSpoolsView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ClientTierRateThrottle]
    throttle_scope = "public_read"

    @extend_schema(tags=["Public printing"], auth=[], responses={200: PublicFilamentSpoolSerializer(many=True), **PUBLIC_PRINT_ERROR_RESPONSES})
    def get(self, request, makerspace_slug):
        makerspace = get_public_makerspace(makerspace_slug)
        _require_module(makerspace)
        spools = FilamentSpool.objects.filter(makerspace=makerspace, is_active=True).order_by("material", "color")
        return Response(PublicFilamentSpoolSerializer(spools, many=True).data)


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
        data = serializer.validated_data
        try:
            content_type = validate_print_upload(data["kind"], data["filename"], data.get("content_type", ""))
        except ValueError as exc:
            raise ValidationError({"file": str(exc)}) from exc
        object_key = print_object_key(makerspace.id, data["kind"])
        upload_file = PrintRequestFile.objects.create(
            makerspace=makerspace, kind=data["kind"], object_key=object_key,
            content_type=content_type, original_filename=data["filename"], owner=request.user,
        )
        return Response({"file_id": upload_file.id, "upload": presigned_print_upload(object_key, content_type)}, status=status.HTTP_201_CREATED)


class PrintRequestSubmitView(APIView):
    permission_classes = [IsActiveRequester]
    throttle_classes = [ClientTierRateThrottle]
    throttle_scope = "print_request_submit"

    @extend_schema(tags=["Public printing"], request=PrintRequestSubmitSerializer, responses={201: PrintRequestSubmitResponseSerializer, **PUBLIC_PRINT_ERROR_RESPONSES})
    def post(self, request, makerspace_slug):
        makerspace = get_public_makerspace(makerspace_slug)
        _require_module(makerspace)
        if _honeypot_filled(request.data):
            decoy = SimpleNamespace(public_token=uuid.uuid4(), status=PrintRequest.Status.PENDING)
            return Response(PrintRequestSubmitResponseSerializer(decoy).data, status=status.HTTP_201_CREATED)
        require_active_member_presence(request.user, makerspace)
        serializer = PrintRequestSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        print_request = public_workflow.submit_public_print_request(makerspace, serializer.validated_data, request.user)
        return Response(PrintRequestSubmitResponseSerializer(print_request).data, status=status.HTTP_201_CREATED)


class PublicPrintStatusView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ClientTierRateThrottle]
    throttle_scope = "request_status"
    serializer_class = PublicPrintStatusSerializer
    lookup_field = "public_token"
    queryset = PrintRequest.objects.filter(bucket__makerspace__archived_at__isnull=True).select_related("bucket__makerspace")

    @extend_schema(tags=["Public printing"], auth=[], responses={200: PublicPrintStatusSerializer, **PUBLIC_PRINT_ERROR_RESPONSES})
    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        serializer = PublicPrintStatusSerializer(obj, context={"request": request, "queue_counts": queue_counts_for(obj.bucket.makerspace, [obj])})
        return Response(serializer.data)
