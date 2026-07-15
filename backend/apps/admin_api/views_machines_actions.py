from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.admin_api.machine_access import resolve_machine
from apps.admin_api.permissions import IsActiveStaff
from apps.machines import access, services
from apps.machines.serializers import (
    LogErrorSerializer,
    LogUsageSerializer,
    MachineErrorLogSerializer,
    MachineSerializer,
    MachineUsageEntrySerializer,
    SetStatusSerializer,
)
from apps.makerspaces.guards import require_module


def _resolved_machine(user, pk):
    machine = resolve_machine(user, pk)
    require_module(machine.makerspace_id, 'machines')
    return machine


class MachineSetStatusView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=['Admin machines'],
        summary='Set a machine status',
        request=SetStatusSerializer,
        responses={
            200: MachineSerializer,
            400: OpenApiResponse(description='Invalid machine status.'),
        },
    )
    def post(self, request, pk, *args, **kwargs):
        machine = _resolved_machine(request.user, pk)
        if not access.can_operate_machine(request.user, machine):
            raise PermissionDenied()
        serializer = SetStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        machine = services.set_status(
            machine,
            request.user,
            serializer.validated_data['status'],
        )
        return Response(MachineSerializer(machine, context={'request': request}).data)


class MachineRetireView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=['Admin machines'],
        summary='Retire a machine',
        request=None,
        responses={200: MachineSerializer},
    )
    def post(self, request, pk, *args, **kwargs):
        machine = _resolved_machine(request.user, pk)
        return Response(
            MachineSerializer(services.retire_machine(machine, request.user), context={'request': request}).data
        )


class MachineUnretireView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=['Admin machines'],
        summary='Reactivate a retired machine',
        request=None,
        responses={200: MachineSerializer},
    )
    def post(self, request, pk, *args, **kwargs):
        machine = _resolved_machine(request.user, pk)
        return Response(
            MachineSerializer(services.unretire_machine(machine, request.user), context={'request': request}).data
        )


class MachineUsageView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=['Admin machines'],
        summary='List machine usage entries',
        request=None,
        responses={200: MachineUsageEntrySerializer(many=True)},
    )
    def get(self, request, pk, *args, **kwargs):
        machine = _resolved_machine(request.user, pk)
        entries = machine.usage_entries.select_related('logged_by').all()
        return Response(MachineUsageEntrySerializer(entries, many=True).data)

    @extend_schema(
        tags=['Admin machines'],
        summary='Log machine usage',
        request=LogUsageSerializer,
        responses={
            201: MachineUsageEntrySerializer,
            400: OpenApiResponse(description='Invalid usage entry.'),
        },
    )
    def post(self, request, pk, *args, **kwargs):
        machine = _resolved_machine(request.user, pk)
        if not access.can_operate_machine(request.user, machine):
            raise PermissionDenied()
        serializer = LogUsageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        entry = services.log_usage(
            machine,
            request.user,
            data['hours'],
            data.get('note', ''),
        )
        return Response(
            MachineUsageEntrySerializer(entry).data,
            status=status.HTTP_201_CREATED,
        )


class MachineErrorLogView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=['Admin machines'],
        summary='List machine error logs',
        request=None,
        responses={200: MachineErrorLogSerializer(many=True)},
    )
    def get(self, request, pk, *args, **kwargs):
        machine = _resolved_machine(request.user, pk)
        rows = machine.error_logs.select_related('logged_by').all()
        return Response(MachineErrorLogSerializer(rows, many=True).data)

    @extend_schema(
        tags=['Admin machines'],
        summary='Log a machine error',
        request=LogErrorSerializer,
        responses={
            201: MachineErrorLogSerializer,
            400: OpenApiResponse(description='Invalid error log.'),
        },
    )
    def post(self, request, pk, *args, **kwargs):
        machine = _resolved_machine(request.user, pk)
        if not access.can_operate_machine(request.user, machine):
            raise PermissionDenied()
        serializer = LogErrorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        row = services.log_error(
            machine,
            request.user,
            data['severity'],
            data['message'],
        )
        return Response(
            MachineErrorLogSerializer(row).data,
            status=status.HTTP_201_CREATED,
        )
