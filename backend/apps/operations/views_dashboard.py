from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff
from apps.hardware_requests.models import (
    HardwareRequest,
    PublicProblemReport,
    PublicToolLoan,
)
from apps.integrations.models import EmailLog
from apps.inventory.models import InventoryProduct
from apps.makerspaces.models import Makerspace
from apps.makerspaces.platform import module_enabled
from apps.operations.models import StocktakeSession
from apps.warranty.models import Warranty


class DashboardSerializer(serializers.Serializer):
    overdue_loans = serializers.IntegerField(required=False, default=0)
    pending_requests = serializers.IntegerField(required=False, default=0)
    awaiting_issue = serializers.IntegerField(required=False, default=0)
    open_problem_reports = serializers.IntegerField(required=False, default=0)
    low_stock = serializers.IntegerField(required=False, default=0)
    pending_prints = serializers.IntegerField(required=False, default=0)
    active_prints = serializers.IntegerField(required=False, default=0)
    prints_awaiting_collection = serializers.IntegerField(required=False, default=0)
    failed_emails = serializers.IntegerField(required=False, default=0)
    stocktakes_awaiting_approval = serializers.IntegerField(required=False, default=0)
    warranty_expiring = serializers.IntegerField(required=False, default=0)
    maintenance_overdue = serializers.IntegerField(required=False, default=0)


@extend_schema(
    tags=["Dashboard"],
    summary="Staff operations dashboard counts",
    request=None,
    responses={
        200: DashboardSerializer,
        403: OpenApiResponse(description="Permission denied."),
        404: OpenApiResponse(description="Makerspace not found."),
    },
)
class DashboardView(APIView):
    permission_classes = [IsActiveStaff]
    http_method_names = ["get", "head", "options"]

    def get(self, request, makerspace_id):
        makerspace = get_object_or_404(
            rbac.scope_by_makerspace(
                request.user,
                Makerspace.objects.filter(archived_at__isnull=True),
                makerspace_field="id",
            ),
            pk=makerspace_id,
        )
        if _is_guest_only(request.user, makerspace.id):
            raise PermissionDenied()
        if not (
            rbac.can(request.user, rbac.Action.VIEW_INVENTORY, makerspace.id)
            or rbac.can(request.user, rbac.Action.MANAGE_PRINTING, makerspace.id)
            or rbac.can(request.user, rbac.Action.MANAGE_MAKERSPACE, makerspace.id)
        ):
            raise PermissionDenied()
        return Response(build_dashboard(makerspace))


def build_dashboard(makerspace):
    now = timezone.now()
    today = timezone.localdate()
    counts = {key: 0 for key in DashboardSerializer().fields}

    try:
        reviewed_overdue = HardwareRequest.objects.filter(
            makerspace=makerspace,
            status__in=[
                HardwareRequest.Status.ISSUED,
                HardwareRequest.Status.PARTIALLY_RETURNED,
            ],
            return_due_at__lt=now,
        ).count()
        direct_overdue = PublicToolLoan.objects.filter(
            makerspace=makerspace,
            returned_at__isnull=True,
            due_at__lt=now,
        ).count()
        counts["overdue_loans"] = reviewed_overdue + direct_overdue
    except Exception:
        pass
    try:
        counts["pending_requests"] = HardwareRequest.objects.filter(
            makerspace=makerspace,
            status=HardwareRequest.Status.PENDING_APPROVAL,
        ).count()
    except Exception:
        pass
    try:
        counts["awaiting_issue"] = HardwareRequest.objects.filter(
            makerspace=makerspace,
            status=HardwareRequest.Status.ACCEPTED,
        ).count()
    except Exception:
        pass
    try:
        counts["open_problem_reports"] = PublicProblemReport.objects.filter(
            makerspace=makerspace,
            resolved_at__isnull=True,
        ).count()
    except Exception:
        pass
    try:
        counts["low_stock"] = InventoryProduct.objects.filter(
            makerspace=makerspace,
            available_quantity=0,
        ).count()
    except Exception:
        pass
    try:
        from apps.machines.models import MachineServiceRequest
        prints = MachineServiceRequest.objects.filter(makerspace=makerspace, queue__machine_type__slug="3d_printer")
        counts["pending_prints"] = prints.filter(status=MachineServiceRequest.Status.PENDING).count()
        counts["active_prints"] = prints.filter(status=MachineServiceRequest.Status.IN_PROGRESS).count()
        counts["prints_awaiting_collection"] = prints.filter(status=MachineServiceRequest.Status.COMPLETED).count()
    except Exception:
        pass
    try:
        counts["failed_emails"] = EmailLog.objects.filter(
            makerspace=makerspace,
            status=EmailLog.Status.FAILED,
            created_at__gte=now - timedelta(days=7),
        ).count()
    except Exception:
        pass
    try:
        counts["stocktakes_awaiting_approval"] = StocktakeSession.objects.filter(
            makerspace=makerspace,
            status=StocktakeSession.Status.COMPLETED,
        ).count()
    except Exception:
        pass
    try:
        counts["warranty_expiring"] = Warranty.objects.filter(
            makerspace=makerspace,
            warranty_expires_on__isnull=False,
            warranty_expires_on__lte=today + timedelta(days=30),
        ).count()
    except Exception:
        pass
    if module_enabled(makerspace, "maintenance"):
        try:
            from apps.maintenance.models import MaintenanceSchedule

            counts["maintenance_overdue"] = MaintenanceSchedule.objects.filter(
                machine__makerspace=makerspace,
                is_active=True,
                next_due__lt=today,
            ).count()
        except Exception:
            pass

    return counts


def _is_guest_only(user, makerspace_id):
    return rbac.is_handout_only(user, makerspace_id)
