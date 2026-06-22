from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.admin_api.permissions import IsActiveStaff
from apps.admin_api.serializers_lending_history import (
    LendingHistoryResponseSerializer,
)
from apps.hardware_requests.display import requester_label
from apps.hardware_requests.models import HardwareRequestItem
from apps.inventory.models import InventoryProduct


def _actor_payload(actor):
    if actor is None:
        return None
    return {
        "username": actor.username,
        "role": actor.role,
    }


class InventoryLendingHistoryView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Admin inventory"],
        summary="Per-item lending history (last borrower + last 3 lends)",
        responses={200: LendingHistoryResponseSerializer},
    )
    def get(self, request, pk):
        from apps.accounts import rbac

        # Product-first scoping 404s for non-audit roles / cross-tenant. The
        # soft-hide also 404s a superadmin querying a makerspace that has opted
        # out of superadmin access, since this exposes borrower PII (mirrors the
        # audit/report soft-hide).
        scoped = rbac.scope_by_action(
            request.user,
            rbac.Action.VIEW_AUDIT,
            InventoryProduct.objects.all(),
        )
        scoped = rbac.hide_from_superadmin(request.user, scoped, "makerspace_id")
        product = get_object_or_404(scoped, pk=pk)
        items = (
            HardwareRequestItem.objects.filter(
                product=product,
                issued_quantity__gt=0,
                request__issued_at__isnull=False,
                request__makerspace_id=product.makerspace_id,
            )
            .select_related(
                "request",
                "request__requester",
                "request__issued_by",
                "request__accepted_by",
            )
            .order_by("-request__issued_at", "-request__id")[:3]
        )
        recent = [
            {
                "id": item.id,
                # Readable borrower label, never the internal checkin_<hash>.
                "username": requester_label(item.request),
                "issued_at": item.request.issued_at,
                "quantity": item.issued_quantity,
                "issued_by": _actor_payload(item.request.issued_by),
                "accepted_by": _actor_payload(item.request.accepted_by),
            }
            for item in items
        ]
        last_borrower = recent[0] if recent else None
        return Response(
            {
                "product_id": product.id,
                "last_borrower": last_borrower,
                "recent": recent,
            }
        )
