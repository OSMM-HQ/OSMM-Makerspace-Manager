from django.db.models import Q
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff
from apps.audit import services as audit
from apps.machines import access
from apps.machines.models import MachineType
from apps.machines.serializers import (
    MachineTypeCreateSerializer,
    MachineTypeSerializer,
)
from apps.makerspaces.guards import require_module


class MachineTypeListCreateView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=['Admin machines'],
        summary='List machine types for a makerspace',
        request=None,
        responses={200: MachineTypeSerializer(many=True)},
    )
    def get(self, request, makerspace_id, *args, **kwargs):
        require_module(makerspace_id, 'machines')
        if not access.can_see_machines(request.user, makerspace_id):
            raise PermissionDenied()
        queryset = MachineType.objects.filter(
            Q(makerspace__isnull=True) | Q(makerspace_id=makerspace_id)
        )
        return Response(MachineTypeSerializer(queryset, many=True).data)

    @extend_schema(
        tags=['Admin machines'],
        summary='Create a custom machine type',
        request=MachineTypeCreateSerializer,
        responses={
            201: MachineTypeSerializer,
            400: OpenApiResponse(description='Invalid machine type.'),
        },
    )
    def post(self, request, makerspace_id, *args, **kwargs):
        require_module(makerspace_id, 'machines')
        if not rbac.can(
            request.user,
            rbac.Action.MANAGE_MACHINES,
            makerspace_id,
        ):
            raise PermissionDenied()
        serializer = MachineTypeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        slug = serializer.validated_data.get("slug")
        if MachineType.objects.filter(makerspace_id=makerspace_id, slug=slug).exists():
            raise ValidationError({"slug": "A machine type with this slug already exists."})
        machine_type = MachineType.objects.create(
            makerspace_id=makerspace_id,
            is_builtin=False,
            managing_action='',
            **serializer.validated_data,
        )
        audit.record(
            request.user,
            'machine_type.created',
            makerspace=machine_type.makerspace,
            target=machine_type,
            target_type='machine_type',
        )
        return Response(
            MachineTypeSerializer(machine_type).data,
            status=status.HTTP_201_CREATED,
        )
