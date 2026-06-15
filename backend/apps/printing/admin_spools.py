from django.contrib import admin, messages
from django.db.models import Q
from unfold.admin import ModelAdmin

from apps.audit import services as audit
from apps.printing.models import FilamentSpool, PrintRequest
from config.admin_access import SuperuserOnlyModelAdmin


@admin.register(FilamentSpool)
class FilamentSpoolAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    actions = ["delete_safely"]
    list_display = (
        "material",
        "color",
        "printer",
        "makerspace",
        "remaining_weight_grams",
        "is_active",
    )
    list_filter = ("material", "is_active", "makerspace", "printer")
    search_fields = (
        "material",
        "color",
        "brand",
        "lot_code",
        "printer__name",
        "makerspace__name",
    )
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "makerspace",
        "printer",
        "material",
        "color",
        "brand",
        "lot_code",
        "initial_weight_grams",
        "remaining_weight_grams",
        "is_active",
        "opened_at",
        "created_at",
        "updated_at",
    )

    def has_delete_permission(self, request, obj=None):
        # Force deletion through the reference-guarded `delete_safely` action only (disables
        # the built-in delete_selected + per-object delete view), so referenced spools can't be
        # hard-deleted and silently SET_NULL request history / requester preferences.
        return False

    @admin.action(description="Safely delete selected spools")
    def delete_safely(self, request, queryset):
        success_count = 0
        for spool in queryset:
            if PrintRequest.objects.filter(
                Q(filament_spool=spool) | Q(requested_filament_spool=spool)
            ).exists():
                self.message_user(
                    request,
                    (
                        f"{spool.pk}: This spool is linked to print requests; "
                        "deactivate it instead to preserve history."
                    ),
                    level=messages.ERROR,
                )
                continue
            audit.record(
                request.user,
                "printing.spool_deleted",
                makerspace=spool.makerspace,
                target=spool,
            )
            spool.delete()
            success_count += 1

        if success_count:
            self.message_user(
                request,
                f"Safely deleted {success_count} spool(s).",
                level=messages.SUCCESS,
            )
