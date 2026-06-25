from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff, require_action
from apps.admin_api.serializers_inventory import InventoryProductAdminSerializer
from apps.admin_api.views_inventory import InventoryPagination
from apps.audit import services as audit
from apps.inventory import availability
from apps.inventory.models import InventoryProduct
from apps.makerspaces.guards import require_module


class NeedsFixShelfListView(generics.ListAPIView):
    """The to-be-fixed shelf: products that currently have units awaiting repair."""

    serializer_class = InventoryProductAdminSerializer
    permission_classes = [IsActiveStaff]
    pagination_class = InventoryPagination

    def get_queryset(self):
        qs = rbac.scope_by_action(
            self.request.user,
            rbac.Action.VIEW_INVENTORY,
            InventoryProduct.objects.select_related("makerspace", "box"),
        ).filter(needs_fix_quantity__gt=0)
        makerspace_id = self.request.query_params.get("makerspace")
        if makerspace_id:
            qs = qs.filter(makerspace_id=makerspace_id)
        else:
            qs = rbac.hide_from_superadmin(self.request.user, qs, "makerspace_id")
        return qs.order_by("name")


class NeedsFixActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["repair", "scrap", "shelve"])
    quantity = serializers.IntegerField(min_value=1)


class NeedsFixActionView(APIView):
    """Move units onto the shelf, back to available, or out of inventory."""

    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Admin inventory"],
        summary="Move inventory units to, from, or out of the to-be-fixed shelf",
        request=NeedsFixActionSerializer,
        responses={200: InventoryProductAdminSerializer},
    )
    def post(self, request, pk, *args, **kwargs):
        product = get_object_or_404(
            rbac.scope_by_action(
                request.user,
                rbac.Action.VIEW_INVENTORY,
                InventoryProduct.objects.select_related("makerspace"),
            ),
            pk=pk,
        )
        require_module(product.makerspace_id, "staff_admin")
        require_action(request.user, rbac.Action.EDIT_INVENTORY, product.makerspace_id)
        serializer = NeedsFixActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            with transaction.atomic():
                if data["action"] == "repair":
                    locked = availability.repair_from_needs_fix(product, data["quantity"])
                elif data["action"] == "shelve":
                    locked = availability.move_available_to_needs_fix(product, data["quantity"])
                else:
                    locked = availability.scrap_from_needs_fix(product, data["quantity"])
                audit.record(
                    request.user,
                    f"inventory.needs_fix_{data['action']}",
                    makerspace=locked.makerspace,
                    target=locked,
                    meta={"quantity": data["quantity"]},
                )
        except availability.InsufficientStock as exc:
            raise ValidationError(str(exc)) from exc
        return Response(InventoryProductAdminSerializer(locked).data)
