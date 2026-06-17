from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.response import Response

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff, require_action
from apps.makerspaces.guards import require_module
from apps.makerspaces.models import Makerspace
from apps.operations import services
from apps.operations.models import StockTransfer
from apps.operations.serializers import StockTransferCreateSerializer, StockTransferSerializer


@extend_schema_view(
    get=extend_schema(tags=["Stock transfers"], summary="List stock transfers", request=None, responses={200: StockTransferSerializer(many=True)}),
    post=extend_schema(tags=["Stock transfers"], summary="Create stock transfer", request=StockTransferCreateSerializer, responses={201: StockTransferSerializer}),
)
class StockTransferListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsActiveStaff]

    def get_serializer_class(self):
        return StockTransferCreateSerializer if self.request.method == "POST" else StockTransferSerializer

    def get_queryset(self):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(makerspace_id, "stock_transfers")
        require_action(self.request.user, rbac.Action.VIEW_INVENTORY, makerspace_id)
        return StockTransfer.objects.filter(makerspace_id=makerspace_id).prefetch_related("lines").order_by("-created_at")

    def create(self, request, *args, **kwargs):
        makerspace = get_object_or_404(Makerspace, pk=self.kwargs["makerspace_id"])
        require_module(makerspace, "stock_transfers")
        # Validate the payload BEFORE the RBAC branch so we can tell an intra-makerspace
        # relocation (allowed for EDIT_INVENTORY holders) from a cross-makerspace move
        # (superadmin-only, since it deducts/credits stock across tenants) — and so no
        # service side effects run for a request the actor isn't allowed to make.
        serializer = StockTransferCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        destination_makerspace_id = (
            serializer.validated_data.get("destination_makerspace_id") or makerspace.id
        )
        is_cross = destination_makerspace_id != makerspace.id
        if is_cross:
            require_action(request.user, rbac.Action.TRANSFER_STOCK, makerspace.id)
            require_action(
                request.user,
                rbac.Action.TRANSFER_STOCK,
                destination_makerspace_id,
            )
        else:
            require_action(request.user, rbac.Action.EDIT_INVENTORY, makerspace.id)
        transfer = services.apply_stock_transfer(request.user, makerspace, serializer.validated_data)
        return Response(StockTransferSerializer(transfer).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(tags=["Stock transfers"], summary="Retrieve stock transfer", request=None, responses={200: StockTransferSerializer}),
)
class StockTransferDetailView(generics.RetrieveAPIView):
    serializer_class = StockTransferSerializer
    permission_classes = [IsActiveStaff]

    def get_queryset(self):
        return rbac.scope_by_action(self.request.user, rbac.Action.VIEW_INVENTORY, StockTransfer.objects.prefetch_related("lines"))
