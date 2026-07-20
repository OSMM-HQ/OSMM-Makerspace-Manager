"""Staff printer pack endpoints backed exclusively by generic machine kernel rows."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff
from apps.admin_api.serializers_machine_service_printer import (
    PrinterPoolCorrectionSerializer, PrinterPoolCreateSerializer, PrinterPoolSerializer,
    TypedManualUsageResponseSerializer, TypedManualUsageSerializer,
)
from apps.machines.models import Machine, MachineConsumablePool, MachineServiceRequest, MachineUsageEntry
from apps.machines.printer_capabilities import PRINTER_SLUG, is_printer_type
from apps.machines.service_consumable_pools import correct_pool, create_pool, log_typed_manual_usage
from apps.makerspaces.guards import require_module
from apps.makerspaces.models import Makerspace


def _space(actor, makerspace_id):
    row = get_object_or_404(rbac.scope_by_makerspace(actor, Makerspace.objects.all(), makerspace_field="id"), pk=makerspace_id)
    require_module(row, "machine_service")
    if not rbac.can(actor, rbac.Action.MANAGE_MACHINES, row.pk):
        raise PermissionDenied()
    return row


def _pool(actor, pk):
    row = get_object_or_404(rbac.scope_by_action(actor, rbac.Action.MANAGE_MACHINES, MachineConsumablePool.objects.select_related("makerspace", "machine__machine_type"), field="makerspace_id"), pk=pk)
    require_module(row.makerspace, "machine_service")
    if not is_printer_type(row.machine.machine_type) if row.machine_id else False:
        raise PermissionDenied()
    return row


class MachineServicePrinterPoolListCreateView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(tags=["Admin machine service"], responses={200: PrinterPoolSerializer(many=True)})
    def get(self, request, makerspace_id):
        space = _space(request.user, makerspace_id)
        rows = MachineConsumablePool.objects.filter(makerspace=space).select_related("machine").order_by("material", "color", "id")
        return Response(PrinterPoolSerializer(rows, many=True).data)

    @extend_schema(tags=["Admin machine service"], request=PrinterPoolCreateSerializer, responses={201: PrinterPoolSerializer})
    def post(self, request, makerspace_id):
        space = _space(request.user, makerspace_id)
        serializer = PrinterPoolCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        machine = None
        if data.get("machine_id"):
            machine = get_object_or_404(Machine.objects.select_related("machine_type").filter(makerspace=space), pk=data["machine_id"])
            if not is_printer_type(machine.machine_type):
                raise PermissionDenied()
        row = create_pool(space, request.user, machine=machine, **{key: value for key, value in data.items() if key != "machine_id"})
        return Response(PrinterPoolSerializer(row).data, status=status.HTTP_201_CREATED)


class MachineServicePrinterPoolDetailView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(tags=["Admin machine service"], responses={200: PrinterPoolSerializer})
    def get(self, request, pk):
        return Response(PrinterPoolSerializer(_pool(request.user, pk)).data)


class MachineServicePrinterPoolAdjustmentView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(tags=["Admin machine service"], request=PrinterPoolCorrectionSerializer, responses={200: PrinterPoolSerializer})
    def post(self, request, pk):
        pool = _pool(request.user, pk)
        serializer = PrinterPoolCorrectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = correct_pool(pool, request.user, **serializer.validated_data)
        return Response(PrinterPoolSerializer(row).data)


class MachineServiceTypedManualUsageView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(tags=["Admin machine service"], responses={200: TypedManualUsageResponseSerializer(many=True)})
    def get(self, request, makerspace_id):
        space = _space(request.user, makerspace_id)
        rows = MachineUsageEntry.objects.filter(machine__makerspace=space, machine__machine_type__slug=PRINTER_SLUG, source=MachineUsageEntry.Source.TYPED_MANUAL)
        return Response(TypedManualUsageResponseSerializer(rows, many=True).data)

    @extend_schema(tags=["Admin machine service"], request=TypedManualUsageSerializer, responses={201: TypedManualUsageResponseSerializer})
    def post(self, request, makerspace_id):
        space = _space(request.user, makerspace_id)
        serializer = TypedManualUsageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        machine = get_object_or_404(Machine.objects.select_related("machine_type").filter(makerspace=space), pk=data.pop("machine_id"))
        if not is_printer_type(machine.machine_type):
            raise PermissionDenied()
        pool_id, request_id = data.pop("consumable_pool_id", None), data.pop("service_request_id", None)
        pool = get_object_or_404(MachineConsumablePool.objects.filter(makerspace=space), pk=pool_id) if pool_id else None
        service_request = get_object_or_404(MachineServiceRequest.objects.filter(makerspace=space), pk=request_id) if request_id else None
        row = log_typed_manual_usage(machine, request.user, pool=pool, service_request=service_request, **data)
        return Response(TypedManualUsageResponseSerializer(row).data, status=status.HTTP_201_CREATED)