from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff
from apps.admin_api.serializers_machine_type_pricing import (
    MachineTypePricingListSerializer, MachineTypePricingSerializer, MachineTypePricingSetSerializer,
)
from apps.audit import services as audit
from apps.machines.models import MachineType, MakerspaceMachineTypePricing
from apps.makerspaces.guards import require_module
from apps.makerspaces.models import Makerspace
from apps.payments.models import MakerspacePaymentSettings


def _authorize(actor, makerspace_id):
    require_module(makerspace_id, "machines")
    if not rbac.is_space_manager_identity(actor, makerspace_id):
        raise PermissionDenied()


def _types(makerspace_id):
    return MachineType.objects.filter(Q(makerspace__isnull=True) | Q(makerspace_id=makerspace_id))


class MachineTypePricingListView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(tags=["Admin machines"], summary="List makerspace machine-type pricing", responses={200: MachineTypePricingListSerializer, 403: OpenApiResponse(description="Space-manager identity required.")})
    def get(self, request, makerspace_id):
        _authorize(request.user, makerspace_id)
        machine_types = list(_types(makerspace_id).only("id"))
        pricing_by_type = {row.machine_type_id: row for row in MakerspaceMachineTypePricing.objects.filter(makerspace_id=makerspace_id, machine_type_id__in=[row.pk for row in machine_types])}
        rows = [pricing_by_type.get(row.pk) or MakerspaceMachineTypePricing(makerspace_id=makerspace_id, machine_type_id=row.pk) for row in machine_types]
        makerspace = get_object_or_404(Makerspace.objects.all(), pk=makerspace_id)
        return Response({"currency": MakerspacePaymentSettings.for_makerspace(makerspace).default_currency, "results": MachineTypePricingSerializer(rows, many=True).data})


class MachineTypePricingDetailView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(tags=["Admin machines"], summary="Set makerspace machine-type pricing", request=MachineTypePricingSetSerializer, responses={200: MachineTypePricingSerializer, 400: OpenApiResponse(description="Invalid price."), 403: OpenApiResponse(description="Space-manager identity required."), 404: OpenApiResponse(description="Machine type not found.")})
    def put(self, request, makerspace_id, machine_type_id):
        _authorize(request.user, makerspace_id)
        machine_type = get_object_or_404(_types(makerspace_id), pk=machine_type_id)
        serializer = MachineTypePricingSetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            row, created = MakerspaceMachineTypePricing.objects.get_or_create(
                makerspace_id=makerspace_id, machine_type=machine_type,
                defaults={**serializer.validated_data, "created_by": request.user, "updated_by": request.user},
            )
            if not created:
                for field, value in serializer.validated_data.items():
                    setattr(row, field, value)
                row.updated_by = request.user
                row.save(update_fields=[*serializer.validated_data.keys(), "updated_by", "updated_at"])
            audit.record(request.user, "machine_type_pricing.set" if created else "machine_type_pricing.updated", makerspace=row.makerspace, target=row, target_type="machine_type_pricing", meta={"machine_type_id": machine_type.pk, "payment_enabled": row.payment_enabled, "rate_per_unit": str(row.rate_per_unit), "flat_fee": str(row.flat_fee)})
        return Response(MachineTypePricingSerializer(row).data)
