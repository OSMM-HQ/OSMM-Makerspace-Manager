from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.admin_api.machine_access import resolve_machine
from apps.admin_api.permissions import IsActiveStaff
from apps.machines import access, services
from apps.machines.serializers import (
    AssignOperatorSerializer,
    MachineOperatorSerializer,
)
from apps.makerspaces.guards import require_module

User = get_user_model()


def _resolved_machine(user, pk):
    machine = resolve_machine(user, pk)
    require_module(machine.makerspace_id, 'machines')
    return machine


class MachineOperatorsView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=['Admin machines'],
        summary='List machine operators',
        request=None,
        responses={200: MachineOperatorSerializer(many=True)},
    )
    def get(self, request, pk, *args, **kwargs):
        machine = _resolved_machine(request.user, pk)
        if not access.can_manage_machine(request.user, machine):
            raise PermissionDenied()
        rows = machine.operators.select_related('user', 'assigned_by').all()
        return Response(MachineOperatorSerializer(rows, many=True).data)

    @extend_schema(
        tags=['Admin machines'],
        summary='Assign a machine operator',
        request=AssignOperatorSerializer,
        responses={
            201: MachineOperatorSerializer,
            400: OpenApiResponse(description='Invalid operator assignment.'),
        },
    )
    def post(self, request, pk, *args, **kwargs):
        machine = _resolved_machine(request.user, pk)
        serializer = AssignOperatorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        target = get_object_or_404(User, pk=data['user_id'])
        row = services.assign_operator(
            machine,
            request.user,
            target,
            data['access_level'],
        )
        return Response(
            MachineOperatorSerializer(row).data,
            status=status.HTTP_201_CREATED,
        )


class MachineOperatorDetailView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=['Admin machines'],
        summary='Update a machine operator',
        request=AssignOperatorSerializer,
        responses={
            200: MachineOperatorSerializer,
            400: OpenApiResponse(description='Invalid operator assignment.'),
        },
    )
    def patch(self, request, pk, user_pk, *args, **kwargs):
        machine = _resolved_machine(request.user, pk)
        target = get_object_or_404(User, pk=user_pk)
        payload = request.data.copy()
        payload['user_id'] = user_pk
        serializer = AssignOperatorSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        row = services.assign_operator(
            machine,
            request.user,
            target,
            serializer.validated_data['access_level'],
        )
        return Response(MachineOperatorSerializer(row).data)

    @extend_schema(
        tags=['Admin machines'],
        summary='Remove a machine operator',
        request=None,
        responses={204: None},
    )
    def delete(self, request, pk, user_pk, *args, **kwargs):
        machine = _resolved_machine(request.user, pk)
        target = get_object_or_404(User, pk=user_pk)
        services.remove_operator(machine, request.user, target)
        return Response(status=status.HTTP_204_NO_CONTENT)
