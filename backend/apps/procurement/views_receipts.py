from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff
from apps.audit import services as audit
from apps.evidence.responses import storage_unavailable_response
from apps.evidence.storage import StorageUnavailable
from apps.makerspaces.guards import require_module
from apps.procurement import access, storage
from apps.procurement.models import ToBuyItem, ToBuyReceipt
from apps.procurement.serializers import (
    ToBuyReceiptFinalizeSerializer,
    ToBuyReceiptPresignSerializer,
    ToBuyReceiptSerializer,
    ToBuyReceiptUploadResponseSerializer,
    ToBuyReceiptUrlSerializer,
)
from apps.procurement.views_items import MODULE_KEY, PROCUREMENT_ERROR_RESPONSES


def _procurement_scope(user):
    return rbac.makerspaces_for_actions(
        user,
        rbac.Action.EDIT_INVENTORY,
        rbac.Action.MANAGE_PRINTING,
    )


def _scope_items(user):
    queryset = ToBuyItem.objects.select_related("makerspace")
    scope = _procurement_scope(user)
    if scope is rbac.ALL:
        return queryset
    if not scope:
        return queryset.none()
    return queryset.filter(makerspace_id__in=scope)


def resolve_item(user, pk):
    item = get_object_or_404(_scope_items(user), pk=pk)
    require_module(item.makerspace, MODULE_KEY)
    if item.kind not in access.viewable_kinds(user, item.makerspace_id):
        raise Http404()
    return item


def _scope_receipts(user):
    queryset = ToBuyReceipt.objects.select_related(
        "to_buy_item",
        "to_buy_item__makerspace",
        "uploaded_by",
    )
    scope = _procurement_scope(user)
    if scope is rbac.ALL:
        return queryset
    if not scope:
        return queryset.none()
    return queryset.filter(to_buy_item__makerspace_id__in=scope)


def resolve_receipt(user, pk):
    receipt = get_object_or_404(_scope_receipts(user), pk=pk)
    item = receipt.to_buy_item
    require_module(item.makerspace, MODULE_KEY)
    if item.kind not in access.viewable_kinds(user, item.makerspace_id):
        raise Http404()
    return receipt


def assert_can_manage(user, item):
    if not access.can_manage_kind(user, item.makerspace_id, item.kind):
        raise PermissionDenied()


@extend_schema(tags=["Procurement"])
class ToBuyReceiptPresignView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        summary="Create a procurement receipt upload URL",
        request=ToBuyReceiptPresignSerializer,
        responses={
            201: ToBuyReceiptUploadResponseSerializer,
            400: OpenApiResponse(description="Invalid receipt upload request."),
            503: OpenApiResponse(description="Receipt storage is unavailable."),
            **PROCUREMENT_ERROR_RESPONSES,
        },
    )
    def post(self, request, pk, *args, **kwargs):
        item = resolve_item(request.user, pk)
        assert_can_manage(request.user, item)
        serializer = ToBuyReceiptPresignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        ext = storage.ext_for(data["content_type"], data["filename"])
        object_key = storage.receipt_object_key(item.makerspace_id, ext)
        try:
            upload = storage.presigned_upload(object_key, data["content_type"])
        except StorageUnavailable:
            return storage_unavailable_response()
        return Response(
            {"object_key": object_key, "upload": upload},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Procurement"])
class ToBuyReceiptListCreateView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        summary="List procurement receipts for a to-buy item",
        responses={200: ToBuyReceiptSerializer(many=True), **PROCUREMENT_ERROR_RESPONSES},
    )
    def get(self, request, pk, *args, **kwargs):
        item = resolve_item(request.user, pk)
        receipts = item.receipts.select_related("uploaded_by").order_by("-created_at", "-id")
        return Response(ToBuyReceiptSerializer(receipts, many=True).data)

    @extend_schema(
        summary="Finalize an uploaded procurement receipt",
        request=ToBuyReceiptFinalizeSerializer,
        responses={
            201: ToBuyReceiptSerializer,
            400: OpenApiResponse(description="Invalid or duplicate procurement receipt."),
            503: OpenApiResponse(description="Receipt storage is unavailable."),
            **PROCUREMENT_ERROR_RESPONSES,
        },
    )
    def post(self, request, pk, *args, **kwargs):
        item = resolve_item(request.user, pk)
        assert_can_manage(request.user, item)
        serializer = ToBuyReceiptFinalizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        object_key = serializer.validated_data["object_key"]
        if ToBuyReceipt.objects.filter(object_key=object_key).exists():
            raise ValidationError({"object_key": "This receipt is already attached."})
        try:
            storage.finalize_receipt_upload(item, object_key)
        except StorageUnavailable:
            return storage_unavailable_response()
        try:
            with transaction.atomic():
                receipt = ToBuyReceipt.objects.create(
                    to_buy_item=item,
                    object_key=object_key,
                    uploaded_by=request.user,
                )
        except IntegrityError as exc:
            raise ValidationError({"object_key": "This receipt is already attached."}) from exc
        audit.record(
            request.user,
            "procurement.receipt_added",
            makerspace=item.makerspace,
            target=receipt,
        )
        return Response(
            ToBuyReceiptSerializer(receipt).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Procurement"])
class ToBuyReceiptUrlView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        summary="Create a signed procurement receipt view URL",
        responses={
            200: ToBuyReceiptUrlSerializer,
            503: OpenApiResponse(description="Receipt storage is unavailable."),
            **PROCUREMENT_ERROR_RESPONSES,
        },
    )
    def get(self, request, pk, *args, **kwargs):
        receipt = resolve_receipt(request.user, pk)
        try:
            url = storage.presigned_get_url(receipt.object_key)
        except StorageUnavailable:
            return storage_unavailable_response()
        return Response({"url": url})


@extend_schema(tags=["Procurement"])
class ToBuyReceiptDeleteView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        summary="Delete a procurement receipt",
        responses={204: None, **PROCUREMENT_ERROR_RESPONSES},
    )
    def delete(self, request, pk, *args, **kwargs):
        receipt = resolve_receipt(request.user, pk)
        item = receipt.to_buy_item
        assert_can_manage(request.user, item)
        audit.record(
            request.user,
            "procurement.receipt_removed",
            makerspace=item.makerspace,
            target=receipt,
        )
        receipt.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

