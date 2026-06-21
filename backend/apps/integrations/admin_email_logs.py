from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.integrations.models import EmailLog
from config.admin_access import SuperuserOnlyModelAdmin


@admin.register(EmailLog)
class EmailLogAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("created_at", "to_email", "stream", "event", "status", "makerspace")
    list_filter = ("status", "stream", "makerspace")
    search_fields = ("to_email", "subject", "event", "error", "makerspace__name")
    readonly_fields = (
        "makerspace",
        "to_email",
        "subject",
        "text_body",
        "html_body",
        "stream",
        "event",
        "audience",
        "connection_kind",
        "status",
        "error",
        "attempts",
        "created_at",
        "updated_at",
        "sent_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
