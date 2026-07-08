from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.notifications.models import Notification
from config.admin_access import SuperuserOnlyModelAdmin


@admin.register(Notification)
class NotificationAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("title", "level", "event", "makerspace", "read_at", "created_at")
    list_filter = ("makerspace", "level", "read_at")
    search_fields = ("title", "body", "event", "makerspace__name", "makerspace__slug")
    readonly_fields = ("created_at",)