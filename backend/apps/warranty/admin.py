from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.warranty.models import Warranty, WarrantyDocument
from config.admin_access import SuperuserOnlyModelAdmin


@admin.register(Warranty)
class WarrantyAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = (
        "id",
        "makerspace",
        "asset",
        "printer",
        "purchased_on",
        "warranty_expires_on",
        "vendor_name",
    )
    list_filter = ("makerspace",)
    search_fields = (
        "vendor_name",
        "vendor_contact",
        "asset__asset_tag",
        "printer__name",
        "makerspace__name",
        "makerspace__slug",
    )
    raw_id_fields = ("makerspace", "asset", "printer")
    readonly_fields = ("created_at", "updated_at")


@admin.register(WarrantyDocument)
class WarrantyDocumentAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("id", "warranty", "original_filename", "content_type", "size_bytes", "created_at")
    list_filter = ("content_type",)
    search_fields = ("original_filename", "object_key", "warranty__vendor_name")
    readonly_fields = (
        "warranty",
        "object_key",
        "original_filename",
        "content_type",
        "size_bytes",
        "uploaded_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
