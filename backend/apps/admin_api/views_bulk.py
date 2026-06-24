from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.admin_api import bulk_import
from apps.admin_api.models import BulkImportJob
from apps.admin_api.permissions import IsActiveStaff, require_action
from apps.admin_api.serializers_bulk import (
    BulkImportJobCreateSerializer,
    BulkImportJobSerializer,
    BulkImportPreviewSerializer,
)
from apps.admin_api.tasks import process_bulk_import_job
from apps.makerspaces.guards import require_module
from apps.makerspaces.models import Makerspace
from apps.openapi import BULK_IMPORT_ROWS_EXAMPLE


def _rows_from_upload(uploaded_file):
    """Parse an uploaded import file, mapping bad-input parse errors to 400.

    rows_from_upload raises ValueError (incl. JSONDecodeError/UnicodeDecodeError,
    and normalized corrupt-XLSX errors) on malformed files; without this they'd
    surface as a 500 for what is really user input."""
    try:
        return bulk_import.rows_from_upload(uploaded_file)
    except ValueError as exc:
        raise ValidationError({"file": str(exc) or "Uploaded file could not be parsed."})


def _authorized_makerspace(request, makerspace_id):
    makerspace = get_object_or_404(Makerspace, pk=makerspace_id)
    require_module(makerspace, "bulk_import")
    require_action(request.user, rbac.Action.EDIT_INVENTORY, makerspace_id)
    return makerspace


class BulkImportPreviewView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Bulk import"],
        summary="Preview inventory bulk import",
        request=BulkImportPreviewSerializer,
        responses={200: OpenApiResponse(description="Import preview with row errors.")},
        examples=[BULK_IMPORT_ROWS_EXAMPLE],
    )
    def post(self, request, makerspace_id, *args, **kwargs):
        makerspace = _authorized_makerspace(request, makerspace_id)
        serializer = BulkImportPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rows = serializer.validated_data.get("rows")
        if rows is None:
            rows = _rows_from_upload(serializer.validated_data["file"])
        return Response(
            bulk_import.preview_import(
                makerspace,
                rows,
                serializer.validated_data.get("mapping") or {},
            )
        )


class BulkImportApplyView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Bulk import"],
        summary="Apply inventory bulk import",
        request=BulkImportPreviewSerializer,
        responses={200: OpenApiResponse(description="Import application result.")},
        examples=[BULK_IMPORT_ROWS_EXAMPLE],
    )
    def post(self, request, makerspace_id, *args, **kwargs):
        makerspace = _authorized_makerspace(request, makerspace_id)
        serializer = BulkImportPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rows = serializer.validated_data.get("rows")
        if rows is None:
            rows = _rows_from_upload(serializer.validated_data["file"])
        result = bulk_import.apply_import(
            request.user,
            makerspace,
            rows,
            serializer.validated_data.get("mapping") or {},
        )
        return Response(result, status=status.HTTP_200_OK)


class BulkImportJobListCreateView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Bulk import"],
        summary="Create an async inventory bulk import job",
        request=BulkImportJobCreateSerializer,
        responses={201: BulkImportJobSerializer},
    )
    def post(self, request, makerspace_id, *args, **kwargs):
        makerspace = _authorized_makerspace(request, makerspace_id)
        serializer = BulkImportJobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rows = serializer.validated_data.get("rows")
        if rows is None:
            rows = _rows_from_upload(serializer.validated_data["file"])
        job = BulkImportJob.objects.create(
            makerspace=makerspace,
            actor=request.user,
            mode=serializer.validated_data["mode"],
            rows=rows,
            mapping=serializer.validated_data.get("mapping") or {},
        )
        process_bulk_import_job.delay(job.id)
        job.refresh_from_db()
        return Response(BulkImportJobSerializer(job).data, status=status.HTTP_201_CREATED)


class BulkImportJobDetailView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Bulk import"],
        summary="Get async inventory bulk import job status",
        responses={200: BulkImportJobSerializer},
    )
    def get(self, request, makerspace_id, job_id, *args, **kwargs):
        _authorized_makerspace(request, makerspace_id)
        job = get_object_or_404(
            BulkImportJob,
            pk=job_id,
            makerspace_id=makerspace_id,
        )
        return Response(BulkImportJobSerializer(job).data)
