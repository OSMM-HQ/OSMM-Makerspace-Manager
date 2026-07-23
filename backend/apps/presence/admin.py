from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.presence.models import PresenceSession
from config.admin_access import SuperuserOnlyModelAdmin


@admin.register(PresenceSession)
class PresenceSessionAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("member", "makerspace", "started_at", "expires_at", "ended_at", "end_reason")
    list_filter = ("makerspace", "end_reason")
    readonly_fields = tuple(field.name for field in PresenceSession._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in ("GET", "HEAD") and super().has_change_permission(request, obj)
