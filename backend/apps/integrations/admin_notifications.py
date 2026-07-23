from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.integrations.models import NotificationDeliveryLog, NotificationPreference
from config.admin_access import SuperuserOnlyModelAdmin


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    """Read-only in /control/; preferences are edited via scoped React settings (Part K)."""

    list_display = ("makerspace", "feature", "channel", "enabled", "updated_at")
    list_filter = ("makerspace", "feature", "channel", "enabled")
    readonly_fields = (
        "makerspace", "feature", "channel", "enabled", "updated_by",
        "created_at", "updated_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NotificationDeliveryLog)
class NotificationDeliveryLogAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    """Read-only durable delivery record for non-email channels. Celery owns retry."""

    list_display = (
        "makerspace", "channel", "feature", "event", "status", "attempts",
        "created_at", "sent_at",
    )
    list_filter = ("makerspace", "channel", "feature", "status")
    readonly_fields = (
        "makerspace", "channel", "feature", "event", "text_body", "payload",
        "status", "error", "attempts", "created_at", "updated_at", "sent_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
