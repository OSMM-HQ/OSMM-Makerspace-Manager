"""Staff-only private attachment endpoints for machine service requests."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff
from apps.admin_api.serializers_machine_service import (
    ServiceFileFinalizeSerializer,
    ServiceFileFinalizeResponseSerializer,
    ServiceFilePresignResponseSerializer,
    ServiceFilePresignSerializer,
    ServiceFileUrlSerializer,
)
from apps.admin_api.views_machine_service import _manageable_request
from apps.evidence.responses import storage_unavailable_response
from apps.evidence.storage import StorageUnavailable
from apps.hardware_requests.exceptions import ErrorSerializer
from apps.machines import service_storage
from apps.machines.models import ServiceRequestFile
from apps.makerspaces.guards import require_module


FILE_ERRORS = {
    400: OpenApiResponse(ErrorSerializer, description="Invalid attachment input."),
    401: OpenApiResponse(description="Authentication required."),
    403: OpenApiResponse(description="Machine management permission required."),
    404: OpenApiResponse(description="Service request or file was not found."),
    409: OpenApiResponse(ErrorSerializer, description="Attachment conflict."),
    503: OpenApiResponse(description="Private storage is unavailable."),
}


def _manageable_file(actor, pk, *, attached=False):
    visible = get_object_or_404(
        rbac.scope_by_makerspace(
            actor,
            ServiceRequestFile.objects.select_related("machine__makerspace", "service_request"),
            makerspace_field="machine__makerspace_id",
        ),
        pk=pk,
    )
    require_module(visible.machine.makerspace, "machine_service")
    if not rbac.can(actor, rbac.Action.MANAGE_MACHINES, visible.machine.makerspace_id):
        raise PermissionDenied()
    field = "service_request__bucket__machine__makerspace_id" if attached else "machine__makerspace_id"
    return get_object_or_404(
        rbac.scope_by_action(
            actor, rbac.Action.MANAGE_MACHINES,
            ServiceRequestFile.objects.select_related("machine__makerspace", "service_request__bucket__machine"),
            field=field,
        ), pk=visible.pk,
    )


class MachineServiceFilePresignView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Admin machine service"], summary="Create a service attachment upload URL",
        request=ServiceFilePresignSerializer,
        responses={201: ServiceFileFinalizeResponseSerializer, **FILE_ERRORS},
    )
    def post(self, request, pk, *args, **kwargs):
        service_request = _manageable_request(request.user, pk)
        serializer = ServiceFilePresignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            upload, presigned = service_storage.create_staged_file(
                service_request, actor=request.user, **serializer.validated_data,
            )
        except StorageUnavailable:
            return storage_unavailable_response()
        return Response({"file_id": upload.pk, "upload": presigned}, status=status.HTTP_201_CREATED)


class MachineServiceFileFinalizeView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Admin machine service"], summary="Finalize a service attachment upload",
        request=ServiceFileFinalizeSerializer,
        responses={201: ServiceFilePresignResponseSerializer, **FILE_ERRORS},
    )
    def post(self, request, pk, *args, **kwargs):
        service_request = _manageable_request(request.user, pk)
        serializer = ServiceFileFinalizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            file = service_storage.finalize_file(
                service_request, actor=request.user, **serializer.validated_data,
            )
        except StorageUnavailable:
            return storage_unavailable_response()
        return Response({"file_id": file.pk}, status=status.HTTP_201_CREATED)


class MachineServiceFileUrlView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Admin machine service"], summary="Create a signed service attachment URL",
        request=None, responses={200: ServiceFileUrlSerializer, **FILE_ERRORS},
    )
    def get(self, request, pk, *args, **kwargs):
        file = _manageable_file(request.user, pk, attached=True)
        if file.service_request_id is None or file.attached_at is None:
            return Response({"detail": "Attachment is not available."}, status=status.HTTP_409_CONFLICT)
        try:
            url = service_storage.presigned_get_url(file.object_key)
        except StorageUnavailable:
            return storage_unavailable_response()
        return Response({"url": url})


class MachineServiceFileDeleteView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Admin machine service"], summary="Delete a staged service attachment",
        request=None, responses={204: None, **FILE_ERRORS},
    )
    def delete(self, request, pk, *args, **kwargs):
        file = _manageable_file(request.user, pk)
        try:
            service_storage.delete_staged_file(file, actor=request.user)
        except StorageUnavailable:
            return storage_unavailable_response()
        return Response(status=status.HTTP_204_NO_CONTENT)
