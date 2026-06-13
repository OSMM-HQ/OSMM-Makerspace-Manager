from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from apps.makerspaces.models import Makerspace, MakerspaceMembership, TenantFrontend


class MakerspaceMembershipInline(TabularInline):
    model = MakerspaceMembership
    fk_name = "makerspace"
    fields = ("user", "role")
    autocomplete_fields = ("user",)
    extra = 0


@admin.register(Makerspace)
class MakerspaceAdmin(ModelAdmin):
    list_display = (
        "name",
        "public_code",
        "slug",
        "location",
        "public_inventory_enabled",
        "updated_at",
    )
    list_filter = ("public_inventory_enabled",)
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "public_code", "slug", "location")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "public_code",
                    "slug",
                    "location",
                    "public_inventory_enabled",
                    "default_loan_days",
                )
            },
        ),
    )
    inlines = (MakerspaceMembershipInline,)


@admin.register(TenantFrontend)
class TenantFrontendAdmin(ModelAdmin):
    list_display = ("makerspace", "frontend_type", "hostname", "is_primary", "is_active", "updated_at")
    list_filter = ("frontend_type", "is_primary", "is_active")
    search_fields = ("makerspace__name", "makerspace__slug", "hostname", "token")
    autocomplete_fields = ("makerspace", "created_by")
    readonly_fields = ("token", "created_at", "updated_at")
