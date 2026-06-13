import csv
from io import BytesIO, StringIO

from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.html import escape
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from openpyxl import Workbook
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff, IsActiveSuperAdmin, require_action
from apps.audit import services as audit
from apps.boxes.models import Box, QrCode, QrScanEvent
from apps.boxes.serializers import BoxSerializer, QrCodeSerializer
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem
from apps.inventory.models import InventoryAsset, InventoryProduct
from apps.makerspaces.models import Makerspace
from apps.makerspaces.guards import require_module
from apps.operations import services
from apps.operations.models import QrPrintBatch, StockTransfer, StocktakeSession
from apps.operations.serializers import (
    AssetGenerateSerializer,
    AssetGenerateResultSerializer,
    ContainerContentsSerializer,
    ContainerHistorySerializer,
    ContainerMoveSerializer,
    EmptySerializer,
    GenericObjectSerializer,
    HealthSerializer,
    QrPrintBatchCreateSerializer,
    QrPrintBatchDetailSerializer,
    QrPrintBatchItemCreateSerializer,
    QrPrintBatchItemResultSerializer,
    QrPrintBatchSerializer,
    ReadinessSerializer,
    StockTransferCreateSerializer,
    StockTransferSerializer,
    StocktakeCreateSerializer,
    StocktakeLineInputSerializer,
    StocktakeLineSerializer,
    StocktakeSerializer,
)


class HealthView(APIView):
    permission_classes = [AllowAny]
    serializer_class = GenericObjectSerializer

    @extend_schema(tags=["Health"], summary="Health check", request=None, responses={200: HealthSerializer})
    def get(self, request, *args, **kwargs):
        return Response({"status": "ok"})


class ReadinessView(APIView):
    permission_classes = [AllowAny]
    serializer_class = GenericObjectSerializer

    @extend_schema(tags=["Health"], summary="Readiness check", request=None, responses={200: ReadinessSerializer})
    def get(self, request, *args, **kwargs):
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return Response({"status": "ready", "database": "ok"})


@extend_schema_view(
    get=extend_schema(tags=["Containers"], summary="List containers", request=None, responses={200: BoxSerializer(many=True)}),
    post=extend_schema(tags=["Containers"], summary="Create container", request=BoxSerializer, responses={201: BoxSerializer}),
)
class ContainerListCreateView(generics.ListCreateAPIView):
    serializer_class = BoxSerializer
    permission_classes = [IsActiveStaff]

    def get_queryset(self):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(makerspace_id, "containers")
        require_action(self.request.user, rbac.Action.VIEW_INVENTORY, makerspace_id)
        return Box.objects.filter(makerspace_id=makerspace_id).order_by("label")

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
        if not (request.user.is_superuser or request.user.role == request.user.Role.SUPERADMIN):
            raise PermissionDenied()
        serializer = StockTransferCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
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


@extend_schema_view(
    get=extend_schema(tags=["Stocktake"], summary="List stocktakes", request=None, responses={200: StocktakeSerializer(many=True)}),
    post=extend_schema(tags=["Stocktake"], summary="Create stocktake", request=StocktakeCreateSerializer, responses={201: StocktakeSerializer}),
)
class StocktakeListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsActiveStaff]

    def get_serializer_class(self):
        return StocktakeCreateSerializer if self.request.method == "POST" else StocktakeSerializer

    def get_queryset(self):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(makerspace_id, "stocktake")
        require_action(self.request.user, rbac.Action.VIEW_INVENTORY, makerspace_id)
        return StocktakeSession.objects.filter(makerspace_id=makerspace_id).prefetch_related("lines").order_by("-started_at")

    def create(self, request, *args, **kwargs):
        makerspace = get_object_or_404(Makerspace, pk=self.kwargs["makerspace_id"])
        require_module(makerspace, "stocktake")
        require_action(request.user, rbac.Action.EDIT_INVENTORY, makerspace.id)
        serializer = StocktakeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        stocktake = services.create_stocktake(request.user, makerspace, serializer.validated_data)
        return Response(StocktakeSerializer(stocktake).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(tags=["Stocktake"], summary="Retrieve stocktake", request=None, responses={200: StocktakeSerializer}),
)
class StocktakeDetailView(generics.RetrieveAPIView):
    serializer_class = StocktakeSerializer
    permission_classes = [IsActiveStaff]

    def get_queryset(self):
        return rbac.scope_by_action(self.request.user, rbac.Action.VIEW_INVENTORY, StocktakeSession.objects.prefetch_related("lines"))


class StocktakeCountLineView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = StocktakeLineInputSerializer

    @extend_schema(tags=["Stocktake"], summary="Count stocktake line", request=StocktakeLineInputSerializer, responses={201: StocktakeLineSerializer})
    def post(self, request, pk, *args, **kwargs):
        stocktake = _stocktake_for_action(request.user, pk, rbac.Action.EDIT_INVENTORY)
        serializer = StocktakeLineInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        line = services.add_stocktake_line(request.user, stocktake, serializer.validated_data)
        return Response(StocktakeLineSerializer(line).data, status=status.HTTP_201_CREATED)


class StocktakeCompleteView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = EmptySerializer

    @extend_schema(tags=["Stocktake"], summary="Complete stocktake", request=EmptySerializer, responses={200: StocktakeSerializer})
    def post(self, request, pk, *args, **kwargs):
        stocktake = _stocktake_for_action(request.user, pk, rbac.Action.EDIT_INVENTORY)
        return Response(StocktakeSerializer(services.complete_stocktake(request.user, stocktake)).data)


class StocktakeApproveView(APIView):
    permission_classes = [IsActiveSuperAdmin]
    serializer_class = EmptySerializer

    @extend_schema(tags=["Stocktake"], summary="Approve stocktake", request=EmptySerializer, responses={200: StocktakeSerializer})
    def post(self, request, pk, *args, **kwargs):
        stocktake = get_object_or_404(StocktakeSession, pk=pk)
        return Response(StocktakeSerializer(services.approve_stocktake(request.user, stocktake)).data)


class StocktakeApplyAdjustmentsView(APIView):
    permission_classes = [IsActiveSuperAdmin]
    serializer_class = EmptySerializer

    @extend_schema(tags=["Stocktake"], summary="Apply stocktake adjustments", request=EmptySerializer, responses={200: StocktakeSerializer})
    def post(self, request, pk, *args, **kwargs):
        stocktake = get_object_or_404(StocktakeSession, pk=pk)
        return Response(StocktakeSerializer(services.apply_stocktake_adjustments(request.user, stocktake)).data)


class AnalyticsView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = GenericObjectSerializer

    @extend_schema(tags=["Analytics"], summary="Get analytics report", request=None, responses={200: OpenApiTypes.OBJECT})
    def get(self, request, makerspace_id, report_key="summary", *args, **kwargs):
        require_action(request.user, rbac.Action.VIEW_INVENTORY, makerspace_id)
        require_module(makerspace_id, "reports")
        return Response(report_data(makerspace_id, report_key))


class ReportExportView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = EmptySerializer

    @extend_schema(
        tags=["Reports"],
        summary="Export report",
        request=None,
        parameters=[
            OpenApiParameter("report_key", OpenApiTypes.STR, OpenApiParameter.PATH),
            OpenApiParameter("format", OpenApiTypes.STR, OpenApiParameter.QUERY, enum=["csv", "xlsx"]),
        ],
        responses={
            (200, "text/csv"): OpenApiTypes.STR,
            (200, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"): OpenApiTypes.BINARY,
        },
    )
    def get(self, request, makerspace_id, report_key, *args, **kwargs):
        require_action(request.user, rbac.Action.VIEW_INVENTORY, makerspace_id)
        require_module(makerspace_id, "reports")
        fmt = request.query_params.get("format", "csv")
        rows = report_rows(makerspace_id, report_key)
        if fmt == "xlsx":
            return _xlsx_response(rows, f"{report_key}.xlsx")
        if fmt != "csv":
            raise ValidationError({"format": "Use csv or xlsx."})
        return _csv_response(rows, f"{report_key}.csv")


@extend_schema_view(
    get=extend_schema(tags=["QR print batches"], summary="List QR print batches", request=None, responses={200: QrPrintBatchSerializer(many=True)}),
    post=extend_schema(tags=["QR print batches"], summary="Create QR print batch", request=QrPrintBatchCreateSerializer, responses={201: QrPrintBatchSerializer}),
)
class QrPrintBatchListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsActiveStaff]

    def get_serializer_class(self):
        return QrPrintBatchCreateSerializer if self.request.method == "POST" else QrPrintBatchSerializer

    def get_queryset(self):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(makerspace_id, "qr_print_batches")
        require_action(self.request.user, rbac.Action.MANAGE_QR, makerspace_id)
        return QrPrintBatch.objects.filter(makerspace_id=makerspace_id).order_by("-created_at")

    def create(self, request, *args, **kwargs):
        makerspace = get_object_or_404(Makerspace, pk=self.kwargs["makerspace_id"])
        require_module(makerspace, "qr_print_batches")
        require_action(request.user, rbac.Action.MANAGE_QR, makerspace.id)
        serializer = QrPrintBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch = QrPrintBatch.objects.create(makerspace=makerspace, title=serializer.validated_data["title"], created_by=request.user)
        audit.record(request.user, "qr_print_batch.created", makerspace=makerspace, target=batch)
        return Response(QrPrintBatchSerializer(batch).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(tags=["QR print batches"], summary="Retrieve QR print batch", request=None, responses={200: QrPrintBatchDetailSerializer}),
)
class QrPrintBatchDetailView(generics.RetrieveAPIView):
    serializer_class = QrPrintBatchDetailSerializer
    permission_classes = [IsActiveStaff]

    def get_queryset(self):
        return rbac.scope_by_action(self.request.user, rbac.Action.MANAGE_QR, QrPrintBatch.objects.prefetch_related("items__qr_code"))


class QrPrintBatchItemView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = QrPrintBatchItemCreateSerializer

    @extend_schema(tags=["QR print batches"], summary="Add QR code to print batch", request=QrPrintBatchItemCreateSerializer, responses={201: QrPrintBatchItemResultSerializer})
    def post(self, request, pk, *args, **kwargs):
        batch = get_object_or_404(rbac.scope_by_action(request.user, rbac.Action.MANAGE_QR, QrPrintBatch.objects.all()), pk=pk)
        require_module(batch.makerspace, "qr_print_batches")
        serializer = QrPrintBatchItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        qr = get_object_or_404(QrCode, pk=serializer.validated_data["qr_code_id"], makerspace=batch.makerspace)
        item = services.add_qr_to_batch(
            batch,
            qr,
            serializer.validated_data.get("label_text", ""),
            serializer.validated_data.get("sort_order"),
        )
        return Response({"id": item.id}, status=status.HTTP_201_CREATED)


class QrPrintBatchPrintView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = EmptySerializer

    @extend_schema(tags=["QR print batches"], summary="Render QR print batch HTML", request=None, responses={(200, "text/html"): OpenApiTypes.STR})
    def get(self, request, pk, *args, **kwargs):
        batch = get_object_or_404(rbac.scope_by_action(request.user, rbac.Action.MANAGE_QR, QrPrintBatch.objects.prefetch_related("items__qr_code")), pk=pk)
        require_module(batch.makerspace, "qr_print_batches")
        html = _batch_html(batch)
        return HttpResponse(html, content_type="text/html")


class AssetGenerateView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = AssetGenerateSerializer

    @extend_schema(tags=["Asset units"], summary="Generate asset units", request=AssetGenerateSerializer, responses={201: AssetGenerateResultSerializer})
    def post(self, request, pk, *args, **kwargs):
        product = get_object_or_404(rbac.scope_by_action(request.user, rbac.Action.MANAGE_QR, InventoryProduct.objects.all()), pk=pk)
        require_module(product.makerspace, "asset_units")
        serializer = AssetGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created, batch = services.generate_assets_with_qr(request.user, product, serializer.validated_data)
        return Response(
            {
                "assets": [
                    {"id": pair["asset"].id, "asset_tag": pair["asset"].asset_tag, "qr": QrCodeSerializer(pair["qr"]).data}
                    for pair in created
                ],
                "print_batch_id": batch.id if batch else None,
            },
            status=status.HTTP_201_CREATED,
        )


class AssetQrView(APIView):
    permission_classes = [IsActiveStaff]
    serializer_class = EmptySerializer

    @extend_schema(tags=["Asset units"], summary="Create asset QR code", request=EmptySerializer, responses={201: QrCodeSerializer})
    def post(self, request, pk, *args, **kwargs):
        asset = get_object_or_404(rbac.scope_by_action(request.user, rbac.Action.MANAGE_QR, InventoryAsset.objects.all()), pk=pk)
        require_module(asset.makerspace, "asset_units")
        qr, _ = QrCode.objects.get_or_create(
            makerspace=asset.makerspace,
            target_type=QrCode.TargetType.ASSET,
            target_id=asset.id,
            status=QrCode.Status.ACTIVE,
            defaults={"created_by": request.user},
        )
        return Response(QrCodeSerializer(qr).data, status=status.HTTP_201_CREATED)


def report_data(makerspace_id, report_key):
    if report_key == "summary":
        return {
            "products": InventoryProduct.objects.filter(makerspace_id=makerspace_id, is_archived=False).count(),
            "assets": InventoryAsset.objects.filter(makerspace_id=makerspace_id).count(),
            "active_loans": HardwareRequest.objects.filter(makerspace_id=makerspace_id, status__in=[HardwareRequest.Status.ISSUED, HardwareRequest.Status.PARTIALLY_RETURNED]).count(),
            "available_quantity": InventoryProduct.objects.filter(makerspace_id=makerspace_id).aggregate(total=Sum("available_quantity"))["total"] or 0,
            "issued_quantity": InventoryProduct.objects.filter(makerspace_id=makerspace_id).aggregate(total=Sum("issued_quantity"))["total"] or 0,
            "damaged_quantity": InventoryProduct.objects.filter(makerspace_id=makerspace_id).aggregate(total=Sum("damaged_quantity"))["total"] or 0,
            "missing_quantity": InventoryProduct.objects.filter(makerspace_id=makerspace_id).aggregate(total=Sum("lost_quantity"))["total"] or 0,
        }
    return {"rows": report_rows(makerspace_id, report_key)}


def report_rows(makerspace_id, report_key):
    if report_key == "taken-items":
        qs = HardwareRequestItem.objects.filter(request__makerspace_id=makerspace_id).values("product__name").annotate(quantity=Sum("issued_quantity")).order_by("-quantity")
        return [["product", "issued_quantity"], *[[row["product__name"], row["quantity"] or 0] for row in qs]]
    if report_key == "active-loans":
        qs = HardwareRequest.objects.filter(makerspace_id=makerspace_id, status__in=[HardwareRequest.Status.ISSUED, HardwareRequest.Status.PARTIALLY_RETURNED]).order_by("-issued_at")
        return [["id", "requester", "status", "issued_at"], *[[r.id, r.requester_username, r.status, r.issued_at] for r in qs]]
    if report_key == "returns":
        qs = HardwareRequest.objects.filter(makerspace_id=makerspace_id, status__in=[HardwareRequest.Status.RETURNED, HardwareRequest.Status.CLOSED_WITH_ISSUE]).order_by("-closed_at")
        return [["id", "requester", "status", "closed_at"], *[[r.id, r.requester_username, r.status, r.closed_at] for r in qs]]
    if report_key == "damaged-missing":
        qs = InventoryProduct.objects.filter(makerspace_id=makerspace_id).order_by("name")
        return [["product", "damaged_quantity", "missing_quantity"], *[[p.name, p.damaged_quantity, p.lost_quantity] for p in qs]]
    if report_key == "qr-scans":
        qs = QrScanEvent.objects.filter(makerspace_id=makerspace_id).values("context").annotate(count=Count("id")).order_by("context")
        return [["context", "count"], *[[row["context"], row["count"]] for row in qs]]
    data = report_data(makerspace_id, "summary")
    return [["metric", "value"], *[[key, value] for key, value in data.items()]]


def _stocktake_for_action(user, pk, action):
    stocktake = get_object_or_404(rbac.scope_by_action(user, action, StocktakeSession.objects.all()), pk=pk)
    require_module(stocktake.makerspace, "stocktake")
    return stocktake


def _csv_response(rows, filename):
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerows(rows)
    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _xlsx_response(rows, filename):
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buffer = BytesIO()
    wb.save(buffer)
    response = HttpResponse(buffer.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _batch_html(batch):
    items = []
    for item in batch.items.select_related("qr_code"):
        items.append(
            f'<article class="label"><div class="payload">{escape(item.qr_code.payload)}</div>'
            f'<strong>{escape(item.label_text)}</strong><small>{escape(item.target_type)} #{item.target_id}</small></article>'
        )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{escape(batch.title)}</title>
<style>
body{{font-family:Arial,sans-serif;margin:24px;color:#111827}}
.sheet{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}}
.label{{border:1px solid #111827;padding:12px;min-height:120px;break-inside:avoid}}
.payload{{font-family:monospace;font-size:12px;margin-bottom:16px;word-break:break-all}}
strong,small{{display:block}}
@media print{{body{{margin:0}}.label{{page-break-inside:avoid}}}}
</style></head><body><h1>{escape(batch.title)}</h1><section class="sheet">{''.join(items)}</section></body></html>"""
