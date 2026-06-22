from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.integrations.models import EmailNotificationMute
from config.admin_access import SuperuserOnlyModelAdmin


@admin.register(EmailNotificationMute)
class EmailNotificationMuteAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = (
        "makerspace",
        "target",
        "stream",
        "event",
        "audience",
        "created_at",
    )
    list_filter = ("makerspace", "stream", "audience")
    readonly_fields = (
        "makerspace",
        "target",
        "stream",
        "event",
        "audience",
        "created_at",
        "created_by",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
