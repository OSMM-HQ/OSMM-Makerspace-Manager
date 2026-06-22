from django.contrib import admin, messages
from unfold.admin import ModelAdmin

from apps.integrations.models import EmailLog
from apps.integrations.services import EmailRetryError, retry_email_log
from config.admin_access import SuperuserOnlyModelAdmin


@admin.register(EmailLog)
class EmailLogAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    actions = ["retry_selected"]
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

    # permissions=["view"] keeps the action available on this read-only admin
    # (has_change_permission is False), tied to view access rather than edit.
    @admin.action(description="Retry selected failed emails", permissions=["view"])
    def retry_selected(self, request, queryset):
        succeeded, skipped = 0, 0
        for log in queryset:
            try:
                retry_email_log(request.user, log)
            except EmailRetryError as exc:
                skipped += 1
                self.message_user(request, f"{log.pk}: {exc}", level=messages.WARNING)
            else:
                succeeded += 1
        self.message_user(
            request,
            f"Retried {succeeded} email log(s); skipped {skipped}.",
            level=messages.SUCCESS if succeeded else messages.WARNING,
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
