from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff
from apps.admin_api.serializers_warranty import WarrantyReportRowSerializer
from apps.admin_api.views_inventory import InventoryPagination
from apps.makerspaces.models import Makerspace
from apps.makerspaces.platform import module_enabled
from apps.warranty.models import Warranty
from apps.warranty.status import STATUS_CHOICES, warranty_status

_VALID_STATUSES = {value for value, _ in STATUS_CHOICES}


class MakerspaceWarrantyReportView(APIView):
    permission_classes = [IsActiveStaff]
    pagination_class = InventoryPagination

    @extend_schema(
        tags=["Admin warranty"],
        summary="List warranty records for a makerspace",
        parameters=[
            OpenApiParameter(
                "status",
                str,
                description="Filter rows by computed warranty status.",
                enum=sorted(_VALID_STATUSES),
            )
        ],
        responses={200: WarrantyReportRowSerializer(many=True)},
    )
    def get(self, request, makerspace_id, *args, **kwargs):
        makerspace = get_object_or_404(
            rbac.scope_by_makerspace(
                request.user,
                Makerspace.objects.filter(archived_at__isnull=True),
                "id",
            ),
            pk=makerspace_id,
        )
        status_filter = request.query_params.get("status")
        if status_filter and status_filter not in _VALID_STATUSES:
            raise ValidationError({"status": "Invalid warranty status filter."})
        rows = _report_rows(request.user, makerspace)
        if status_filter:
            rows = [row for row in rows if row["status"] == status_filter]
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(rows, request, view=self)
        serializer = WarrantyReportRowSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


def _report_rows(user, makerspace):
    today = timezone.localdate()
    makerspace_id = makerspace.id
    rows = []
    # Mirror the per-host module guard the individual endpoints apply (require_module):
    # a disabled host module must not expose its warranty rows here either.
    if rbac.can(user, rbac.Action.EDIT_INVENTORY, makerspace_id) and module_enabled(
        makerspace, "staff_admin"
    ):
        rows.extend(_asset_row(warranty, today) for warranty in _asset_warranties(makerspace_id))
    if rbac.can(user, rbac.Action.MANAGE_PRINTING, makerspace_id) and module_enabled(
        makerspace, "printing"
    ):
        rows.extend(
            _printer_row(warranty, today) for warranty in _printer_warranties(makerspace_id)
        )
    return sorted(rows, key=lambda row: (row["host_kind"], row["host_label"].lower()))


def _asset_warranties(makerspace_id):
    return (
        Warranty.objects.filter(asset__makerspace_id=makerspace_id)
        .select_related("asset")
        .annotate(document_count=Count("documents"))
        .order_by("asset__asset_tag")
    )


def _printer_warranties(makerspace_id):
    return (
        Warranty.objects.filter(printer__makerspace_id=makerspace_id)
        .select_related("printer")
        .annotate(document_count=Count("documents"))
        .order_by("printer__name")
    )


def _asset_row(warranty, today):
    asset = warranty.asset
    return _base_row(warranty, today) | {
        "host_kind": "asset",
        "host_id": asset.id,
        "host_label": asset.asset_tag,
        "serial_number": asset.serial_number or None,
    }


def _printer_row(warranty, today):
    printer = warranty.printer
    label = f"{printer.name} ({printer.model})" if printer.model else printer.name
    return _base_row(warranty, today) | {
        "host_kind": "printer",
        "host_id": printer.id,
        "host_label": label,
        "serial_number": None,
    }


def _base_row(warranty, today):
    return {
        "vendor_name": warranty.vendor_name,
        "purchased_on": warranty.purchased_on,
        "warranty_expires_on": warranty.warranty_expires_on,
        "status": warranty_status(warranty, today),
        "document_count": warranty.document_count,
    }
