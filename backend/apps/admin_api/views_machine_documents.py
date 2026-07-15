from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.admin_api.machine_access import (
    resolve_machine,
    resolve_machine_document,
)
from apps.admin_api.permissions import IsActiveStaff
from apps.evidence.responses import storage_unavailable_response
from apps.evidence.storage import StorageUnavailable
from apps.machines import access, services, storage
from apps.machines.serializers import (
    DocumentFinalizeSerializer,
    DocumentPresignSerializer,
    MachineDocumentSerializer,
)
from apps.makerspaces.guards import require_module


def _resolved_machine(user, pk):
    machine = resolve_machine(user, pk)
    require_module(machine.makerspace_id, 'machines')
    return machine


def _resolved_document(user, pk):
    document = resolve_machine_document(user, pk)
    require_module(document.machine.makerspace_id, 'machines')
    return document


class MachineDocumentPresignView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=['Admin machines'],
        summary='Create a machine document upload URL',
        request=DocumentPresignSerializer,
        responses={
            201: OpenApiResponse(description='Machine document upload details.'),
            400: OpenApiResponse(description='Invalid document upload request.'),
            503: OpenApiResponse(
                description='Machine document storage is unavailable.'
            ),
        },
    )
    def post(self, request, pk, *args, **kwargs):
        machine = _resolved_machine(request.user, pk)
        if not access.can_manage_machine(request.user, machine):
            raise PermissionDenied()
        serializer = DocumentPresignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        ext = storage.ext_for(data['content_type'], data['filename'])
        object_key = storage.machine_object_key(machine.makerspace_id, ext)
        try:
            upload = storage.presigned_upload(object_key, data['content_type'])
        except StorageUnavailable:
            return storage_unavailable_response()
        return Response(
            {'object_key': object_key, 'upload': upload},
            status=status.HTTP_201_CREATED,
        )


class MachineDocumentsView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=['Admin machines'],
        summary='List machine documents',
        request=None,
        responses={200: MachineDocumentSerializer(many=True)},
    )
    def get(self, request, pk, *args, **kwargs):
        machine = _resolved_machine(request.user, pk)
        if not access.can_manage_machine(request.user, machine):
            raise PermissionDenied()
        return Response(
            MachineDocumentSerializer(machine.documents.all(), many=True).data
        )

    @extend_schema(
        tags=['Admin machines'],
        summary='Finalize a machine document upload',
        request=DocumentFinalizeSerializer,
        responses={
            201: MachineDocumentSerializer,
            400: OpenApiResponse(description='Invalid machine document.'),
            503: OpenApiResponse(
                description='Machine document storage is unavailable.'
            ),
        },
    )
    def post(self, request, pk, *args, **kwargs):
        machine = _resolved_machine(request.user, pk)
        if not access.can_manage_machine(request.user, machine):
            raise PermissionDenied()
        serializer = DocumentFinalizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            document = services.attach_document(
                machine,
                request.user,
                data['object_key'],
                data['doc_type'],
                data['original_filename'],
            )
        except StorageUnavailable:
            return storage_unavailable_response()
        return Response(
            MachineDocumentSerializer(document).data,
            status=status.HTTP_201_CREATED,
        )


class MachineDocumentUrlView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=['Admin machines'],
        summary='Create a signed machine document view URL',
        request=None,
        responses={
            200: OpenApiResponse(description='Signed machine document URL.'),
            503: OpenApiResponse(
                description='Machine document storage is unavailable.'
            ),
        },
    )
    def get(self, request, pk, *args, **kwargs):
        document = _resolved_document(request.user, pk)
        if not access.can_manage_machine(request.user, document.machine):
            raise PermissionDenied()
        try:
            url = storage.presigned_get_url(document.object_key)
        except StorageUnavailable:
            return storage_unavailable_response()
        return Response({'url': url})


class MachineDocumentDeleteView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=['Admin machines'],
        summary='Delete a machine document',
        request=None,
        responses={204: None},
    )
    def delete(self, request, pk, *args, **kwargs):
        document = _resolved_document(request.user, pk)
        machine = document.machine
        if not access.can_manage_machine(request.user, machine):
            raise PermissionDenied()
        services.remove_document(machine, request.user, document)
        return Response(status=status.HTTP_204_NO_CONTENT)
