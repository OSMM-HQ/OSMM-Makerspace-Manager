from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.procurement.models import ToBuyItem, ToBuyReceipt
from config.admin_access import SuperuserOnlyModelAdmin


@admin.register(ToBuyItem)
class ToBuyItemAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = (
        "name",
        "makerspace",
        "kind",
        "quantity",
        "status",
        "vendor_name",
        "purchaser",
        "created_by",
        "created_at",
    )
    list_filter = ("kind", "status", "makerspace")
    search_fields = ("name", "link", "vendor_name", "makerspace__name", "makerspace__slug")
    readonly_fields = ("created_by", "purchaser", "ordered_at", "received_at", "created_at", "updated_at")
    fields = (
        "makerspace",
        "kind",
        "name",
        "quantity",
        "link",
        "status",
        "estimated_unit_cost",
        "vendor_name",
        "actual_unit_cost",
        "purchaser",
        "ordered_at",
        "received_at",
        "created_by",
        "created_at",
        "updated_at",
    )


@admin.register(ToBuyReceipt)
class ToBuyReceiptAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("id", "to_buy_item", "uploaded_by", "created_at")
    search_fields = ("object_key", "to_buy_item__name", "to_buy_item__makerspace__name")
    readonly_fields = ("to_buy_item", "object_key", "uploaded_by", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
