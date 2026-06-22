from django.contrib import admin
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin

from apps.boxes.models import QrCode
from apps.boxes.qr_render import render_qr_label_svg
from apps.inventory.models import InventoryAsset
from config.admin_access import SuperuserOnlyModelAdmin


@admin.register(InventoryAsset)
class InventoryAssetAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("asset_tag", "product", "makerspace", "box", "status", "updated_at")
    list_filter = ("makerspace", "status")
    search_fields = ("asset_tag", "serial_number", "product__name")
    autocomplete_fields = ("makerspace", "product", "box")
    list_select_related = ("makerspace", "product", "box")
    readonly_fields = ("qr_preview",)

    def qr_preview(self, obj):
        if not obj or not obj.pk:
            return "(save first)"
        qr = QrCode.objects.filter(
            target_type=QrCode.TargetType.ASSET,
            target_id=obj.pk,
            makerspace=obj.makerspace,
            status=QrCode.Status.ACTIVE,
        ).first()
        if not qr:
            return "(no active QR)"
        return mark_safe(render_qr_label_svg(qr.payload, obj.asset_tag))

    qr_preview.short_description = "QR preview"
