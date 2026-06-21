from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.integrations.models import EmailTemplate
from config.admin_access import SuperuserOnlyModelAdmin


@admin.register(EmailTemplate)
class EmailTemplateAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = (
        "makerspace",
        "stream",
        "audience",
        "key",
        "is_active",
        "updated_at",
    )
    list_filter = ("stream", "audience", "key", "is_active", "makerspace")
    search_fields = ("subject", "text_body", "html_body", "makerspace__name")
    autocomplete_fields = ("makerspace",)
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "makerspace",
        "stream",
        "audience",
        "key",
        "subject",
        "text_body",
        "html_body",
        "is_active",
        "created_at",
        "updated_at",
    )
