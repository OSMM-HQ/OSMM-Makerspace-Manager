from django.contrib import admin

from unfold.admin import ModelAdmin

from apps.machines import services
from apps.machines.models import (
    Machine,
    MachineConsumable,
    MachineDocument,
    MachineErrorLog,
    MachineOperator,
    MachineType,
    MachineUsageEntry,
)
from config.admin_access import SuperuserOnlyModelAdmin


@admin.register(MachineType)
class MachineTypeAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("id", "slug", "name", "makerspace", "is_builtin", "managing_action")
    list_filter = ("is_builtin", "makerspace")
    search_fields = ("slug", "name", "makerspace__name")
    raw_id_fields = ("makerspace",)
    readonly_fields = ("is_builtin", "managing_action")

    # Built-in global types are load-bearing (printer auto-link resolves 3d_printer)
    # and are only restored by the seed migration — never let the admin delete them.
    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_builtin:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Machine)
class MachineAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("id", "name", "makerspace", "machine_type", "status", "is_active")
    list_filter = ("status", "is_active", "makerspace", "machine_type")
    search_fields = ("name", "location", "makerspace__name")
    raw_id_fields = ("makerspace", "machine_type", "linked_print_printer", "created_by")
    # status/is_active/link are service-owned — never raw-edited in the admin.
    readonly_fields = (
        "status",
        "is_active",
        "linked_print_printer",
        "image_key",
        "created_by",
        "created_at",
        "updated_at",
    )
    actions = ["retire_selected", "unretire_selected", "mark_maintenance", "mark_idle"]

    # No hard delete of machines anywhere — retirement is the only lifecycle action.
    def has_delete_permission(self, request, obj=None):
        return False

    def _run(self, request, queryset, fn, label):
        done, failed = 0, 0
        for machine in queryset:
            try:
                fn(machine, request.user)
                done += 1
            except Exception as exc:  # surface, never 500 the changelist
                failed += 1
                self.message_user(request, f"{machine}: {exc}", level="ERROR")
        if done:
            self.message_user(request, f"{label} {done} machine(s).")

    @admin.action(description="Retire selected machines")
    def retire_selected(self, request, queryset):
        self._run(request, queryset, services.retire_machine, "Retired")

    @admin.action(description="Reactivate selected machines")
    def unretire_selected(self, request, queryset):
        self._run(request, queryset, services.unretire_machine, "Reactivated")

    @admin.action(description="Set status: maintenance")
    def mark_maintenance(self, request, queryset):
        self._run(
            request, queryset,
            lambda m, u: services.set_status(m, u, Machine.Status.MAINTENANCE),
            "Set maintenance on",
        )

    @admin.action(description="Set status: idle")
    def mark_idle(self, request, queryset):
        self._run(
            request, queryset,
            lambda m, u: services.set_status(m, u, Machine.Status.IDLE),
            "Set idle on",
        )


class _ReadOnlyMachineChildAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MachineOperator)
class MachineOperatorAdmin(_ReadOnlyMachineChildAdmin):
    # Read-only in /control/: operator rows are only ever written through the
    # assignment service (active-membership validation, delegation rules, audit).
    list_display = ("id", "machine", "user", "access_level", "assigned_by", "assigned_at")
    list_filter = ("access_level",)
    search_fields = ("machine__name", "user__username")


@admin.register(MachineUsageEntry)
class MachineUsageEntryAdmin(_ReadOnlyMachineChildAdmin):
    list_display = ("id", "machine", "hours", "source", "logged_by", "created_at")
    list_filter = ("source",)
    search_fields = ("machine__name",)


@admin.register(MachineDocument)
class MachineDocumentAdmin(_ReadOnlyMachineChildAdmin):
    list_display = ("id", "machine", "doc_type", "original_filename", "content_type", "created_at")
    list_filter = ("doc_type", "content_type")
    search_fields = ("machine__name", "original_filename", "object_key")


@admin.register(MachineErrorLog)
class MachineErrorLogAdmin(_ReadOnlyMachineChildAdmin):
    list_display = ("id", "machine", "severity", "logged_by", "created_at")
    list_filter = ("severity",)
    search_fields = ("machine__name", "message")


@admin.register(MachineConsumable)
class MachineConsumableAdmin(_ReadOnlyMachineChildAdmin):
    list_display = (
        "id", "machine", "measurement", "product", "label", "remaining", "created_at"
    )
    list_filter = ("measurement",)
    search_fields = ("machine__name", "product__name", "label")
