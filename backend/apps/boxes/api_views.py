from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.accounts.models import User
from apps.admin_api.permissions import IsActiveStaff
from apps.audit import services as audit
from apps.boxes.access import locked_qr_for_action, makerspace_for_action, qr_for_action
from apps.boxes.models import Box, QrCode, QrScanEvent
from apps.boxes.qr_render import render_qr_label_svg
from apps.boxes.serializers import (
    BoxSerializer,
    CreateBoxQrSerializer,
    CreateToolQrSerializer,
    QrCodeSerializer,
    QrRebindResultSerializer,
    QrRebindTargetSerializer,
    QrResolveResultSerializer,
    QrResolveSerializer,
    QrScanResultSerializer,
    QrScanSerializer,
    qr_target_payload,
)
from apps.boxes.rebind import rebind_qr_target
from apps.boxes.services import revoke_qr_code
from apps.inventory.models import InventoryAsset, InventoryProduct, TrackingMode
from apps.makerspaces.guards import require_module
from apps.makerspaces.platform import module_enabled
from apps.openapi import QR_BOX_EXAMPLE, QR_SCAN_EXAMPLE


class QrPermissionMixin:
    permission_classes = [IsActiveStaff]

    def _require_qr(self, user, makerspace_id):
        require_module(makerspace_id, "qr_management")
        if (
            user.access_status != User.AccessStatus.ACTIVE
            or not rbac.can(user, rbac.Action.MANAGE_QR, makerspace_id)
        ):
            raise PermissionDenied()


class CreateBoxQrView(QrPermissionMixin, APIView):
    @extend_schema(
        tags=["QR assets"],
        summary="Create a QR-coded box",
        request=CreateBoxQrSerializer,
        responses={201: BoxSerializer},
        examples=[QR_BOX_EXAMPLE],
    )
    def post(self, request, *args, **kwargs):
        serializer = CreateBoxQrSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        makerspace = makerspace_for_action(request.user, rbac.Action.MANAGE_QR, data["makerspace_id"])
        self._require_qr(request.user, makerspace.id)
        parent = None
        if data.get("parent_id"):
            parent = get_object_or_404(Box, pk=data["parent_id"], makerspace=makerspace)
        box = Box.objects.create(
            makerspace=makerspace,
            parent=parent,
            label=data["label"],
            location=data.get("location", ""),
            description=data.get("description", ""),
        )
        QrCode.objects.create(
            makerspace=makerspace,
            payload=box.code,
            target_type=QrCode.TargetType.BOX,
            target_id=box.id,
            created_by=request.user,
        )
        audit.record(request.user, "qr.box_created", makerspace=makerspace, target=box)
        return Response(BoxSerializer(box).data, status=status.HTTP_201_CREATED)


class CreateToolQrView(QrPermissionMixin, APIView):
    @extend_schema(
        tags=["QR assets"],
        summary="Create or reuse a QR code for a product or asset",
        request=CreateToolQrSerializer,
        responses={201: QrCodeSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = CreateToolQrSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        makerspace = makerspace_for_action(request.user, rbac.Action.MANAGE_QR, data["makerspace_id"])
        self._require_qr(request.user, makerspace.id)
        if data.get("asset_id"):
            target = get_object_or_404(InventoryAsset, pk=data["asset_id"], makerspace=makerspace)
            target_type = QrCode.TargetType.ASSET
        else:
            target = get_object_or_404(InventoryProduct, pk=data["product_id"], makerspace=makerspace)
            target_type = QrCode.TargetType.PRODUCT
        qr, created = QrCode.objects.get_or_create(
            makerspace=makerspace,
            target_type=target_type,
            target_id=target.id,
            status=QrCode.Status.ACTIVE,
            defaults={"created_by": request.user},
        )
        audit.record(
            request.user,
            "qr.tool_created" if created else "qr.tool_reused",
            makerspace=makerspace,
            target=target,
            meta={"qr_id": qr.id},
        )
        return Response(QrCodeSerializer(qr).data, status=status.HTTP_201_CREATED)


class QrScanView(QrPermissionMixin, APIView):
    @extend_schema(
        tags=["QR assets"],
        summary="Record a QR scan",
        description="Context is limited to issue or return and scan events are immutable.",
        request=QrScanSerializer,
        responses={201: QrScanResultSerializer},
        examples=[QR_SCAN_EXAMPLE],
    )
    def post(self, request, *args, **kwargs):
        serializer = QrScanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        qr = qr_for_action(request.user, rbac.Action.MANAGE_QR, payload=data["payload"], status=QrCode.Status.ACTIVE)
        self._require_qr(request.user, qr.makerspace_id)
        request_id = data.get("request_id")
        if request_id is not None:
            from apps.hardware_requests.models import HardwareRequest

            # The immutable scan inherits the QR's makerspace; a cross-tenant
            # request_id would silently mis-attribute it. Bind them.
            if not HardwareRequest.objects.filter(
                pk=request_id, makerspace_id=qr.makerspace_id
            ).exists():
                raise ValidationError({"request_id": "Request belongs to a different makerspace."})
        scan = QrScanEvent.objects.create(
            makerspace=qr.makerspace,
            qr_code=qr,
            actor=request.user,
            context=data["context"],
            request_id=request_id,
        )
        audit.record(
            request.user,
            "qr.scanned",
            makerspace=qr.makerspace,
            target=qr,
            meta={"context": scan.context, "scan_id": scan.id},
        )
        return Response(
            {
                "qr": QrCodeSerializer(qr).data,
                "target": qr_target_payload(qr),
                "scan_id": scan.id,
            },
            status=status.HTTP_201_CREATED,
        )


class QrResolveView(QrPermissionMixin, APIView):
    @extend_schema(
        tags=["QR assets"],
        summary="Resolve QR target and scanner allowed actions",
        request=QrResolveSerializer,
        responses={200: QrResolveResultSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = QrResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        qr = qr_for_action(request.user, rbac.Action.VIEW_INVENTORY, payload=serializer.validated_data["payload"], status=QrCode.Status.ACTIVE)
        require_module(qr.makerspace, "scanner")
        QrScanEvent.objects.create(
            makerspace=qr.makerspace,
            qr_code=qr,
            actor=request.user,
            context=QrScanEvent.Context.SCANNER_LOOKUP,
        )
        return Response(
            {
                "qr": QrCodeSerializer(qr).data,
                "target": qr_target_payload(qr),
                "allowed_actions": _allowed_scanner_actions(request.user, qr),
            }
        )


class QrPrintView(QrPermissionMixin, APIView):
    @extend_schema(
        tags=["QR assets"],
        summary="Render QR label SVG",
        responses={200: OpenApiResponse(description="SVG QR label.")},
    )
    def get(self, request, pk, *args, **kwargs):
        qr = qr_for_action(request.user, rbac.Action.MANAGE_QR, pk=pk)
        self._require_qr(request.user, qr.makerspace_id)
        return Response(
            {
                "payload": qr.payload,
                "svg": render_qr_label_svg(qr.payload),
                "target": qr_target_payload(qr),
            }
        )


class QrRevokeView(QrPermissionMixin, APIView):
    @extend_schema(
        tags=["QR assets"],
        summary="Revoke active QR code",
        request=None,
        responses={200: QrCodeSerializer},
    )
    def post(self, request, pk, *args, **kwargs):
        qr = locked_qr_for_action(request.user, rbac.Action.MANAGE_QR, pk=pk)
        self._require_qr(request.user, qr.makerspace_id)
        revoke_qr_code(request.user, qr)
        return Response(QrCodeSerializer(qr).data)


class QrRebindTargetView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["QR assets"],
        summary=(
            "Rebind a saved QR to another product/asset "
            "(cross-makerspace = superadmin) and optionally rename"
        ),
        request=QrRebindTargetSerializer,
        responses={
            200: QrRebindResultSerializer,
            409: OpenApiResponse(description="Outstanding loan or target QR conflict."),
        },
    )
    def post(self, request, pk, *args, **kwargs):
        serializer = QrRebindTargetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from django.db import transaction

        with transaction.atomic():
            result = rebind_qr_target(request.user, pk, serializer.validated_data)
        return Response(
            {
                "qr": QrCodeSerializer(result.qr).data,
                "target": qr_target_payload(result.qr),
            }
        )


def _allowed_scanner_actions(user, qr):
    actions = ["view"]
    if module_enabled(qr.makerspace, "scanner") and rbac.can(
        user,
        rbac.Action.MANAGE_QR,
        qr.makerspace_id,
    ):
        actions.append("record_scan")
    if qr.target_type in {QrCode.TargetType.PRODUCT, QrCode.TargetType.ASSET, QrCode.TargetType.BOX}:
        if module_enabled(qr.makerspace, "self_checkout"):
            from apps.hardware_requests.self_checkout_workflow import qr_has_active_loan

            if qr_has_active_loan(qr.makerspace, qr):
                actions.append("return")
            elif _qr_checkout_eligible(qr, require_public=True):
                actions.append("checkout")
        if (
            module_enabled(qr.makerspace, "self_checkout")
            and rbac.can(user, rbac.Action.ISSUE_DIRECT_LOAN, qr.makerspace_id)
            and _qr_checkout_eligible(qr, require_public=False)
        ):
            actions.append("direct_handout")
    if qr.target_type == QrCode.TargetType.BOX:
        actions.append("contents")
        if rbac.can(user, rbac.Action.MANAGE_QR, qr.makerspace_id):
            actions.append("move_container")
    if rbac.can(user, rbac.Action.MANAGE_QR, qr.makerspace_id):
        actions.append("revoke")
    return sorted(set(actions))


def _qr_checkout_eligible(qr, *, require_public):
    if qr.target_type == QrCode.TargetType.PRODUCT:
        product = InventoryProduct.objects.filter(pk=qr.target_id, makerspace=qr.makerspace).first()
        return _product_checkout_eligible(product, require_public=require_public)
    if qr.target_type == QrCode.TargetType.ASSET:
        asset = (
            InventoryAsset.objects.select_related("product")
            .filter(pk=qr.target_id, makerspace=qr.makerspace)
            .first()
        )
        return _asset_checkout_eligible(asset, require_public=require_public)
    if qr.target_type == QrCode.TargetType.BOX:
        return _box_checkout_eligible(qr, require_public=require_public)
    return False


def _product_checkout_eligible(product, *, require_public):
    if product is None or product.is_archived or product.available_quantity < 1:
        return False
    if product.tracking_mode == TrackingMode.INDIVIDUAL:
        return False
    if require_public and (not product.is_public or not product.public_self_checkout_enabled):
        return False
    return True


def _asset_checkout_eligible(asset, *, require_public):
    if asset is None or asset.status != InventoryAsset.Status.AVAILABLE:
        return False
    product = asset.product
    if product is None or product.is_archived or product.available_quantity < 1:
        return False
    if require_public and (
        not asset.public_self_checkout_enabled
        or not product.is_public
        or not product.public_self_checkout_enabled
    ):
        return False
    return True


def _box_checkout_eligible(qr, *, require_public):
    from apps.hardware_requests.models import PublicToolLoan

    box = Box.objects.filter(pk=qr.target_id, makerspace=qr.makerspace).first()
    if box is None or not box.is_active:
        return False
    if PublicToolLoan.objects.filter(
        makerspace=qr.makerspace,
        container=box,
        status=PublicToolLoan.Status.CHECKED_OUT,
    ).exists():
        return False
    asset_filters = {
        "box": box,
        "status": InventoryAsset.Status.AVAILABLE,
        "product__is_archived": False,
        "product__available_quantity__gte": 1,
    }
    product_filters = {
        "box": box,
        "is_archived": False,
        "available_quantity__gte": 1,
    }
    if require_public:
        asset_filters.update(
            {
                "public_self_checkout_enabled": True,
                "product__is_public": True,
                "product__public_self_checkout_enabled": True,
            }
        )
        product_filters.update(
            {"is_public": True, "public_self_checkout_enabled": True}
        )
    if InventoryAsset.objects.filter(**asset_filters).exists():
        return True
    products = InventoryProduct.objects.filter(**product_filters)
    if products.filter(tracking_mode=TrackingMode.INDIVIDUAL).exists():
        return False
    return products.exists()
