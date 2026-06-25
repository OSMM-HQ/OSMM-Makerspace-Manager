import csv
from io import StringIO

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff
from apps.audit import services as audit
from apps.makerspaces.guards import require_module
from apps.makerspaces.models import Makerspace
from apps.printing.serializers import ErrorSerializer
from apps.procurement import access
from apps.procurement.models import ToBuyItem
from apps.procurement.serializers import ToBuyItemSerializer

MODULE_KEY = "procurement"
DEFAULT_LIST_LIMIT = 200
MAX_LIST_LIMIT = 500


PROCUREMENT_ERROR_RESPONSES = {
    400: OpenApiResponse(ErrorSerializer, description="Invalid request."),
    401: OpenApiResponse(description="Authentication credentials were not provided."),
    403: OpenApiResponse(description="Permission denied."),
    404: OpenApiResponse(description="Not found."),
}


def _csv_safe(value):
    # Prevent CSV/spreadsheet formula injection: a cell starting with one of these
    # is treated as a formula by Excel/Sheets. User-controlled name/link could
    # carry one, so neutralize it with a leading apostrophe.
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def _list_limit(request):
    raw = request.query_params.get("limit", DEFAULT_LIST_LIMIT)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_LIST_LIMIT
    if value < 1:
        return DEFAULT_LIST_LIMIT
    return min(value, MAX_LIST_LIMIT)



STATUS_PARAM = OpenApiParameter(
    "status", OpenApiTypes.STR, OpenApiParameter.QUERY,
    enum=[ToBuyItem.Status.PENDING, ToBuyItem.Status.BOUGHT],
    description="Filter by procurement item status.",
)


def _apply_status_filter(queryset, request):
    status = request.query_params.get("status")
    if status in ToBuyItem.Status.values:
        return queryset.filter(status=status)
    return queryset


KIND_PARAM = OpenApiParameter(
    "kind", OpenApiTypes.STR, OpenApiParameter.QUERY,
    enum=[ToBuyItem.Kind.HARDWARE, ToBuyItem.Kind.PRINTING],
    description="Stream to add to. Honored only for makerspace admins/superadmin; "
    "other roles are auto-tagged by role.",
)


@extend_schema(tags=["Procurement"])
class ToBuyListCreateView(generics.ListCreateAPIView):
    serializer_class = ToBuyItemSerializer
    permission_classes = [IsActiveStaff]
    pagination_class = None

    def get_queryset(self):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(get_object_or_404(Makerspace, pk=makerspace_id), MODULE_KEY)
        kinds = access.viewable_kinds(self.request.user, makerspace_id)
        if not kinds:
            return ToBuyItem.objects.none()
        limit = _list_limit(self.request)
        queryset = ToBuyItem.objects.filter(makerspace_id=makerspace_id, kind__in=kinds)
        queryset = _apply_status_filter(queryset, self.request)
        return queryset.select_related("created_by").order_by("-created_at", "-id")[:limit]

    @extend_schema(
        summary="List to-buy items for a makerspace",
        parameters=[OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY), STATUS_PARAM],
        responses={200: ToBuyItemSerializer(many=True), **PROCUREMENT_ERROR_RESPONSES},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(summary="Add a to-buy item", parameters=[KIND_PARAM], responses={201: ToBuyItemSerializer, **PROCUREMENT_ERROR_RESPONSES})
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def perform_create(self, serializer):
        makerspace_id = self.kwargs["makerspace_id"]
        makerspace = get_object_or_404(Makerspace, pk=makerspace_id)
        require_module(makerspace, MODULE_KEY)
        if not access.can_use(self.request.user, makerspace_id):
            raise PermissionDenied()
        kind = access.derive_kind(
            self.request.user,
            makerspace_id,
            self.request.query_params.get("kind"),
        )
        item = serializer.save(
            makerspace=makerspace,
            kind=kind,
            created_by=self.request.user,
        )
        audit.record(
            self.request.user,
            "procurement.item_added",
            makerspace=makerspace,
            target=item,
        )


@extend_schema(tags=["Procurement"])
class ToBuyDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ToBuyItemSerializer
    permission_classes = [IsActiveStaff]
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        # 404-before-403: limit to makerspaces where the actor has any procurement
        # access; get_object() then narrows to the viewable stream.
        scope = rbac.makerspaces_for_actions(
            self.request.user,
            rbac.Action.EDIT_INVENTORY,
            rbac.Action.MANAGE_PRINTING,
        )
        queryset = ToBuyItem.objects.all()
        if scope is rbac.ALL:
            return queryset
        if not scope:
            return queryset.none()
        return queryset.filter(makerspace_id__in=scope)

    def get_object(self):
        obj = super().get_object()
        require_module(obj.makerspace, MODULE_KEY)
        if obj.kind not in access.viewable_kinds(self.request.user, obj.makerspace_id):
            raise Http404()
        return obj

    def _assert_can_manage(self, item):
        if not access.can_manage_kind(self.request.user, item.makerspace_id, item.kind):
            raise PermissionDenied()

    @extend_schema(summary="Retrieve a to-buy item", responses={200: ToBuyItemSerializer, **PROCUREMENT_ERROR_RESPONSES})
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(summary="Update a to-buy item", request=ToBuyItemSerializer, responses={200: ToBuyItemSerializer, **PROCUREMENT_ERROR_RESPONSES})
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    @extend_schema(summary="Delete a to-buy item", responses={204: None, **PROCUREMENT_ERROR_RESPONSES})
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)

    def perform_update(self, serializer):
        self._assert_can_manage(serializer.instance)
        item = serializer.save()
        audit.record(
            self.request.user,
            "procurement.item_updated",
            makerspace=item.makerspace,
            target=item,
        )

    def perform_destroy(self, instance):
        self._assert_can_manage(instance)
        audit.record(
            self.request.user,
            "procurement.item_removed",
            makerspace=instance.makerspace,
            target=instance,
        )
        instance.delete()


@extend_schema(tags=["Procurement"])
class ToBuyExportView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = ToBuyItemSerializer

    @extend_schema(
        summary="Export to-buy items as CSV",
        parameters=[STATUS_PARAM],
        responses={(200, "text/csv"): OpenApiTypes.STR, **PROCUREMENT_ERROR_RESPONSES},
    )
    def get(self, request, makerspace_id, *args, **kwargs):
        require_module(get_object_or_404(Makerspace, pk=makerspace_id), MODULE_KEY)
        kinds = access.viewable_kinds(request.user, makerspace_id)
        if not kinds:
            raise PermissionDenied()
        items = ToBuyItem.objects.filter(makerspace_id=makerspace_id, kind__in=kinds)
        items = (
            _apply_status_filter(items, request)
            .select_related("created_by")
            .order_by("-created_at", "-id")
        )
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            ["kind", "name", "quantity", "link", "status", "estimated_unit_cost", "added_by", "created_at"]
        )
        for item in items:
            writer.writerow([
                _csv_safe(item.kind),
                _csv_safe(item.name),
                item.quantity,
                _csv_safe(item.link),
                _csv_safe(item.status),
                item.estimated_unit_cost if item.estimated_unit_cost is not None else "",
                _csv_safe(item.created_by.username if item.created_by else ""),
                item.created_at.isoformat(),
            ])
        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="to-buy.csv"'
        return response
