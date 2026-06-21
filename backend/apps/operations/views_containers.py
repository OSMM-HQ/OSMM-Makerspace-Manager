from django.db.models import OuterRef, Subquery
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView


class ContainerPagination(PageNumberPagination):
    # Opt-in larger pages (?page_size=) so callers that need the FULL container list
    # (the direct-handout dropdown + its scan-membership check) aren't capped at page one.
    page_size_query_param = "page_size"
    max_page_size = 1000

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff, require_action
from apps.audit import services as audit
from apps.boxes.models import Box, QrCode, QrScanEvent
from apps.boxes.serializers import BoxSerializer
from apps.makerspaces.guards import require_module
from apps.operations.serializers import (
    ContainerContentsSerializer,
    ContainerHistorySerializer,
    ContainerMoveSerializer,
    GenericObjectSerializer,
)


@extend_schema_view(
    get=extend_schema(tags=["Containers"], summary="List containers", request=None, responses={200: BoxSerializer(many=True)}),
    post=extend_schema(tags=["Containers"], summary="Create container", request=BoxSerializer, responses={201: BoxSerializer}),
)
class ContainerListCreateView(generics.ListCreateAPIView):
    serializer_class = BoxSerializer
    permission_classes = [IsActiveStaff]
    pagination_class = ContainerPagination

    def get_queryset(self):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(makerspace_id, "containers")
        require_action(self.request.user, rbac.Action.VIEW_INVENTORY, makerspace_id)
        active_qr = QrCode.objects.filter(
            makerspace_id=OuterRef("makerspace_id"),
            target_type=QrCode.TargetType.BOX,
            target_id=OuterRef("pk"),
            status=QrCode.Status.ACTIVE,
        ).order_by("id").values("id")[:1]
        return Box.objects.filter(makerspace_id=makerspace_id).annotate(_active_qr_code_id=Subquery(active_qr)).order_by("label")

    def perform_create(self, serializer):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(makerspace_id, "containers")
        require_action(self.request.user, rbac.Action.MANAGE_QR, makerspace_id)
        parent = serializer.validated_data.get("parent")
        if parent and parent.makerspace_id != makerspace_id:
            raise ValidationError({"parent": "Parent belongs to a different makerspace."})
        box = serializer.save(makerspace_id=makerspace_id)
        QrCode.objects.get_or_create(
            makerspace_id=makerspace_id,
            target_type=QrCode.TargetType.BOX,
            target_id=box.id,
            status=QrCode.Status.ACTIVE,
            defaults={"payload": box.code, "created_by": self.request.user},
        )
        audit.record(self.request.user, "container.created", makerspace=box.makerspace, target=box)


@extend_schema_view(
    get=extend_schema(tags=["Containers"], summary="Retrieve container", request=None, responses={200: BoxSerializer}),
    patch=extend_schema(tags=["Containers"], summary="Update container", request=BoxSerializer, responses={200: BoxSerializer}),
)
class ContainerDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = BoxSerializer
    permission_classes = [IsActiveStaff]
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        action = rbac.Action.MANAGE_QR if self.request.method == "PATCH" else rbac.Action.VIEW_INVENTORY
        return rbac.scope_by_action(self.request.user, action, Box.objects.all())


class ContainerMoveView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(tags=["Containers"], summary="Move or update container", request=ContainerMoveSerializer, responses={200: BoxSerializer})
    def post(self, request, pk, *args, **kwargs):
        box = get_object_or_404(rbac.scope_by_action(request.user, rbac.Action.MANAGE_QR, Box.objects.all()), pk=pk)
        require_module(box.makerspace, "containers")
        serializer = ContainerMoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "parent_id" in data:
            box.parent = None if data["parent_id"] is None else get_object_or_404(Box, pk=data["parent_id"], makerspace=box.makerspace)
        for field in ("label", "location", "description", "is_active"):
            if field in data:
                setattr(box, field, data[field])
        box.full_clean()
        box.save()
        audit.record(request.user, "container.moved", makerspace=box.makerspace, target=box)
        return Response(BoxSerializer(box).data)


class ContainerContentsView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = GenericObjectSerializer

    @extend_schema(tags=["Containers"], summary="Get container contents", request=None, responses={200: ContainerContentsSerializer})
    def get(self, request, pk, *args, **kwargs):
        box = get_object_or_404(rbac.scope_by_action(request.user, rbac.Action.VIEW_INVENTORY, Box.objects.all()), pk=pk)
        require_module(box.makerspace, "containers")
        return Response(
            {
                "container": BoxSerializer(box).data,
                "products": [
                    {"id": p.id, "name": p.name, "available_quantity": p.available_quantity, "tracking_mode": p.tracking_mode}
                    for p in box.products.filter(is_archived=False).order_by("name")
                ],
                "assets": [
                    {"id": a.id, "asset_tag": a.asset_tag, "product": a.product.name, "status": a.status}
                    for a in box.assets.select_related("product").order_by("asset_tag")
                ],
                "children": BoxSerializer(box.children.order_by("label"), many=True).data,
            }
        )


class ContainerHistoryView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = GenericObjectSerializer

    @extend_schema(tags=["Containers"], summary="Get container scan history", request=None, responses={200: ContainerHistorySerializer})
    def get(self, request, pk, *args, **kwargs):
        box = get_object_or_404(rbac.scope_by_action(request.user, rbac.Action.VIEW_INVENTORY, Box.objects.all()), pk=pk)
        require_module(box.makerspace, "containers")
        scans = QrScanEvent.objects.filter(makerspace=box.makerspace, qr_code__target_type=QrCode.TargetType.BOX, qr_code__target_id=box.id).order_by("-created_at")[:100]
        return Response({"container": box.id, "scans": [{"id": s.id, "context": s.context, "actor": s.actor_id, "created_at": s.created_at} for s in scans]})
