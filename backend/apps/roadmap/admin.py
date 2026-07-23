from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.roadmap.models import RoadmapItem
from config.admin_access import SuperuserOnlyModelAdmin


@admin.register(RoadmapItem)
class RoadmapItemAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = (
        "title",
        "status",
        "category",
        "order",
        "is_public",
        "published_at",
        "updated_at",
    )
    list_filter = ("status", "is_public", "category")
    search_fields = ("title", "description", "category")
    list_editable = ("order", "is_public")
    ordering = ("order", "-published_at", "id")
    readonly_fields = ("created_at", "updated_at")
