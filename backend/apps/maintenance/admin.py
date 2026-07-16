from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.maintenance.models import (
    MaintenanceLog,
    MaintenanceLogDocument,
    MaintenanceSchedule,
)
from config.admin_access import SuperuserOnlyModelAdmin


class _ReadOnlyMaintenanceAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MaintenanceSchedule)
class MaintenanceScheduleAdmin(_ReadOnlyMaintenanceAdmin):
    list_display = (
        "id", "machine", "description", "next_due", "interval_days", "is_active",
    )
    list_filter = ("is_active", "next_due")
    search_fields = ("machine__name", "machine__makerspace__name", "description")
    raw_id_fields = ("machine", "created_by")


@admin.register(MaintenanceLog)
class MaintenanceLogAdmin(_ReadOnlyMaintenanceAdmin):
    list_display = ("id", "machine", "performed_by", "performed_at", "cost")
    list_filter = ("performed_at",)
    search_fields = ("machine__name", "machine__makerspace__name", "summary")
    raw_id_fields = ("machine", "performed_by")


@admin.register(MaintenanceLogDocument)
class MaintenanceLogDocumentAdmin(_ReadOnlyMaintenanceAdmin):
    list_display = (
        "id", "log", "machine", "object_key", "size_bytes", "uploaded_by", "created_at",
    )
    search_fields = (
        "object_key", "log__machine__name", "log__machine__makerspace__name",
    )
    raw_id_fields = ("log", "uploaded_by")

    @admin.display(description="Machine")
    def machine(self, obj):
        return obj.log.machine

