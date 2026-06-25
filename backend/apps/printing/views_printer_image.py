from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff, require_action
from apps.admin_api.serializers_inventory import (
    PublicImageAttachRequestSerializer,
    PublicImageUploadRequestSerializer,
    PublicImageUploadResponseSerializer,
)
from apps.audit import services as audit
from apps.evidence.responses import storage_unavailable_response
from apps.evidence.storage import StorageUnavailable
from apps.inventory import public_image_storage
from apps.makerspaces.guards import require_module
from apps.printing.models import PrintPrinter
from apps.printing.serializers import PrintPrinterSerializer


class PrinterImageView(APIView):
    permission_classes = [IsActiveStaff]

    def _printer(self, request, pk):
        printer = get_object_or_404(
            rbac.scope_by_action(
                request.user,
                rbac.Action.MANAGE_PRINTING,
                PrintPrinter.objects.select_related("makerspace"),
                field="makerspace_id",
            ),
            pk=pk,
        )
        require_action(request.user, rbac.Action.MANAGE_PRINTING, printer.makerspace_id)
        require_module(printer.makerspace_id, "printing")
        return printer

    @extend_schema(
        tags=["Admin printing"],
        summary="Create a printer image upload URL",
        request=PublicImageUploadRequestSerializer,
        responses={
            201: PublicImageUploadResponseSerializer,
            400: OpenApiResponse(description="Invalid image upload request."),
            503: OpenApiResponse(description="Public image storage is unavailable."),
        },
    )
    def post(self, request, pk, *args, **kwargs):
        printer = self._printer(request, pk)
        serializer = PublicImageUploadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        content_type = serializer.validated_data["content_type"]
        ext = public_image_storage.ext_for(
            content_type,
            serializer.validated_data["filename"],
        )
        object_key = public_image_storage.build_object_key(
            "printers",
            printer.makerspace_id,
            ext,
        )
        try:
            upload = public_image_storage.presigned_upload(object_key, content_type)
        except StorageUnavailable:
            return storage_unavailable_response()
        return Response(
            PublicImageUploadResponseSerializer({"object_key": object_key, **upload}).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        tags=["Admin printing"],
        summary="Attach an uploaded image to a printer",
        request=PublicImageAttachRequestSerializer,
        responses={
            200: PrintPrinterSerializer,
            400: OpenApiResponse(description="Invalid image object key or size."),
            503: OpenApiResponse(description="Public image storage is unavailable."),
        },
    )
    def put(self, request, pk, *args, **kwargs):
        printer = self._printer(request, pk)
        serializer = PublicImageAttachRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        object_key = serializer.validated_data["object_key"]
        expected_prefix = f"printers/{printer.makerspace_id}/"
        if not object_key.startswith(expected_prefix):
            raise ValidationError({"object_key": "Image object key is outside this makerspace."})
        if not public_image_storage.is_safe_object_key(object_key):
            raise ValidationError({"object_key": "Invalid image object key."})
        if public_image_storage.public_image_key_in_use(
            printer.makerspace_id,
            object_key,
            printer_id=printer.pk,
        ):
            raise ValidationError({"object_key": "This image is already in use."})
        try:
            result = public_image_storage.finalize_upload(object_key)
        except StorageUnavailable:
            return storage_unavailable_response()
        if result.status != "ok":
            if result.status in {"empty", "too_large"}:
                public_image_storage.delete_object(object_key)
                public_image_storage.delete_object(
                    public_image_storage.staging_key(object_key)
                )
            raise ValidationError(
                {"object_key": public_image_storage.finalize_error_message(result)}
            )
        try:
            is_valid_image = public_image_storage.sniff_is_valid_image(object_key)
        except StorageUnavailable:
            return storage_unavailable_response()
        if not is_valid_image:
            public_image_storage.delete_object(object_key)
            public_image_storage.delete_object(public_image_storage.staging_key(object_key))
            raise ValidationError(
                {"object_key": "Uploaded file is not a valid image."}
            )
        old_key = printer.image_key
        if old_key and old_key != object_key:
            public_image_storage.delete_object(old_key)
        printer.image_key = object_key
        printer.save(update_fields=["image_key", "updated_at"])
        audit.record(
            request.user,
            "printing.printer_image_attached",
            makerspace=printer.makerspace,
            target=printer,
        )
        return Response(PrintPrinterSerializer(printer).data)

    @extend_schema(
        tags=["Admin printing"],
        summary="Clear a printer image",
        responses={200: PrintPrinterSerializer},
    )
    def delete(self, request, pk, *args, **kwargs):
        printer = self._printer(request, pk)
        old_key = printer.image_key
        if old_key:
            public_image_storage.delete_object(old_key)
        printer.image_key = ""
        printer.save(update_fields=["image_key", "updated_at"])
        audit.record(
            request.user,
            "printing.printer_image_cleared",
            makerspace=printer.makerspace,
            target=printer,
        )
        return Response(PrintPrinterSerializer(printer).data)
