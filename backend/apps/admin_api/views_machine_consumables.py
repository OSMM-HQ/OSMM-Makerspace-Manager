from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.admin_api.machine_access import resolve_machine
from apps.admin_api.permissions import IsActiveStaff
from apps.inventory.availability import InsufficientStock
from apps.inventory.models import InventoryProduct, TrackingMode
from apps.machines import access, services_consumables
from apps.machines.models import MachineConsumable
from apps.machines.serializers_consumables import (
    ConsumableCandidateSerializer,
    LinkMachineConsumableSerializer,
    LogMachineConsumptionSerializer,
    MachineConsumableSerializer,
)
from apps.makerspaces.guards import require_module


def _machine_for(user, pk, capability):
    machine = resolve_machine(user, pk)
    if not capability(user, machine):
        raise PermissionDenied()
    require_module(machine.makerspace_id, "machines")
    return machine


def _consumable_ref(cid):
    return MachineConsumable(pk=cid)


class MachineConsumablesView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Admin machines"],
        summary="List machine consumables",
        request=None,
        responses={
            200: MachineConsumableSerializer(many=True),
            403: OpenApiResponse(description="Machine operation is not permitted."),
            404: OpenApiResponse(description="Machine not found."),
        },
    )
    def get(self, request, pk, *args, **kwargs):
        machine = _machine_for(request.user, pk, access.can_operate_machine)
        rows = machine.consumables.select_related("product").all()
        return Response(MachineConsumableSerializer(rows, many=True).data)

    @extend_schema(
        tags=["Admin machines"],
        summary="Link a count or grams consumable to a machine",
        request=LinkMachineConsumableSerializer,
        responses={
            201: MachineConsumableSerializer,
            400: OpenApiResponse(description="Invalid consumable."),
            403: OpenApiResponse(description="Machine management is not permitted."),
            404: OpenApiResponse(description="Machine not found."),
        },
    )
    def post(self, request, pk, *args, **kwargs):
        machine = _machine_for(request.user, pk, access.can_manage_machine)
        serializer = LinkMachineConsumableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = services_consumables.link_consumable(
            machine, request.user, **serializer.validated_data
        )
        return Response(
            MachineConsumableSerializer(row).data,
            status=status.HTTP_201_CREATED,
        )


class MachineConsumableDetailView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Admin machines"],
        summary="Unlink a machine consumable",
        request=None,
        responses={
            204: None,
            400: OpenApiResponse(description="Consumable is not linked."),
            403: OpenApiResponse(description="Machine management is not permitted."),
            404: OpenApiResponse(description="Machine not found."),
        },
    )
    def delete(self, request, pk, cid, *args, **kwargs):
        machine = _machine_for(request.user, pk, access.can_manage_machine)
        services_consumables.unlink_consumable(
            machine, request.user, _consumable_ref(cid)
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MachineConsumptionLogView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Admin machines"],
        summary="Log machine consumable usage",
        request=LogMachineConsumptionSerializer,
        responses={
            200: MachineConsumableSerializer,
            400: OpenApiResponse(description="Invalid quantity or insufficient stock."),
            403: OpenApiResponse(description="Machine operation is not permitted."),
            404: OpenApiResponse(description="Machine not found."),
        },
    )
    def post(self, request, pk, cid, *args, **kwargs):
        machine = _machine_for(request.user, pk, access.can_operate_machine)
        serializer = LogMachineConsumptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            row = services_consumables.log_consumption(
                machine,
                request.user,
                _consumable_ref(cid),
                serializer.validated_data["quantity"],
            )
        except InsufficientStock as exc:
            raise ValidationError({"quantity": str(exc)}) from None
        return Response(MachineConsumableSerializer(row).data)


class MachineConsumableCandidatesView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Admin machines"],
        summary="List inventory products eligible as count consumables",
        request=None,
        responses={
            200: ConsumableCandidateSerializer(many=True),
            403: OpenApiResponse(description="Machine operation is not permitted."),
            404: OpenApiResponse(description="Machine not found."),
        },
    )
    def get(self, request, pk, *args, **kwargs):
        machine = _machine_for(request.user, pk, access.can_operate_machine)
        products = InventoryProduct.objects.filter(
            makerspace_id=machine.makerspace_id,
            tracking_mode=TrackingMode.QUANTITY,
            is_archived=False,
        ).order_by("name", "id")
        return Response(ConsumableCandidateSerializer(products, many=True).data)
