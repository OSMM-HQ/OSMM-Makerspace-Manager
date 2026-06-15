from django import forms
from django.contrib import admin
from django.contrib import messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.template.response import TemplateResponse
from django.utils.safestring import mark_safe
from rest_framework.exceptions import ValidationError as DRFValidationError
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import (
    BooleanRadioFilter,
    ChoicesDropdownFilter,
    RangeDateTimeFilter,
    RangeNumericFilter,
    RelatedDropdownFilter,
)

from apps.boxes.models import QrCode
from apps.boxes.qr_render import render_qr_label_svg
from apps.inventory import availability
from apps.inventory.models import Category, InventoryAsset, InventoryProduct
from apps.operations import services as operations_services
from apps.operations.serializers import AssetGenerateSerializer
from config.admin_access import SuperuserOnlyModelAdmin


class InventoryQuantityAdjustmentForm(forms.Form):
    delta_available = forms.IntegerField(required=True)
    delta_damaged = forms.IntegerField(required=True)
    delta_lost = forms.IntegerField(required=True)
    reason = forms.CharField(required=True, widget=forms.Textarea)


@admin.register(Category)
class CategoryAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("name", "makerspace", "display_order", "slug")
    list_filter = (("makerspace", RelatedDropdownFilter),)
    search_fields = ("name", "slug", "makerspace__name")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("makerspace",)
    ordering = ("display_order", "name")


@admin.register(InventoryProduct)
class InventoryProductAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    actions = ["generate_qr_assets", "adjust_quantities"]
    list_display = (
        "name",
        "category",
        "makerspace",
        "box",
        "is_public",
        "public_availability_mode",
        "available_quantity",
        "total_quantity",
        "is_archived",
        "updated_at",
    )
    list_filter = (
        ("makerspace", RelatedDropdownFilter),
        ("category", RelatedDropdownFilter),
        ("box", RelatedDropdownFilter),
        ("public_availability_mode", ChoicesDropdownFilter),
        ("is_public", BooleanRadioFilter),
        ("is_archived", BooleanRadioFilter),
        ("show_public_count", BooleanRadioFilter),
        ("available_quantity", RangeNumericFilter),
        ("total_quantity", RangeNumericFilter),
        ("updated_at", RangeDateTimeFilter),
    )
    search_fields = ("name", "description", "makerspace__name", "makerspace__slug")
    # Admin autocomplete is not yet tenant-scoped; deferred to Phase 2 RBAC.
    # InventoryProduct.clean() is the safety net.
    autocomplete_fields = ("makerspace", "category", "box")
    list_select_related = ("makerspace", "category", "box")
    ordering = ("name",)
    date_hierarchy = "updated_at"
    list_filter_submit = True
    list_per_page = 50

    @admin.action(description="Generate QR assets for selected inventory")
    def generate_qr_assets(self, request, queryset):
        if "apply" not in request.POST:
            context = {
                **self.admin_site.each_context(request),
                "title": "Generate QR assets",
                "queryset": queryset,
                "opts": self.model._meta,
                "action_name": "generate_qr_assets",
                "action_checkbox_name": ACTION_CHECKBOX_NAME,
            }
            return TemplateResponse(request, "admin/inventory/generate_qr_assets.html", context)

        payload = {
            "count": request.POST.get("count"),
            "name_prefix": request.POST.get("name_prefix", ""),
            "create_print_batch": bool(request.POST.get("create_print_batch")),
        }
        print_batch_id = request.POST.get("print_batch_id", "").strip()
        if print_batch_id:
            payload["print_batch_id"] = print_batch_id
        serial_numbers = [
            value.strip()
            for value in request.POST.get("serial_numbers", "").replace(",", "\n").splitlines()
            if value.strip()
        ]
        if serial_numbers:
            payload["serial_numbers"] = serial_numbers

        serializer = AssetGenerateSerializer(data=payload)
        if not serializer.is_valid():
            self.message_user(request, serializer.errors, level=messages.ERROR)
            return None

        success_count = 0
        asset_count = 0
        for product in queryset:
            try:
                created, _batch = operations_services.generate_assets_with_qr(
                    request.user,
                    product,
                    serializer.validated_data,
                )
            except (DRFValidationError, DjangoValidationError, ObjectDoesNotExist) as exc:
                self.message_user(request, f"{product.pk}: {exc}", level=messages.ERROR)
            else:
                success_count += 1
                asset_count += len(created)

        if success_count:
            self.message_user(
                request,
                f"Generated {asset_count} QR asset(s) for {success_count} product(s).",
                level=messages.SUCCESS,
            )
        return None

    @admin.action(description="Adjust selected inventory quantities")
    def adjust_quantities(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request,
                "Select exactly one inventory product to adjust quantities.",
                level=messages.ERROR,
            )
            return None

        product = queryset.first()
        if "apply" not in request.POST:
            context = {
                **self.admin_site.each_context(request),
                "title": "Adjust inventory quantities",
                "queryset": queryset,
                "opts": self.model._meta,
                "action_name": "adjust_quantities",
                "action_checkbox_name": ACTION_CHECKBOX_NAME,
                "product": product,
            }
            return TemplateResponse(
                request,
                "admin/inventory/adjust_quantities.html",
                context,
            )

        form = InventoryQuantityAdjustmentForm(request.POST)
        if not form.is_valid():
            self.message_user(request, form.errors, level=messages.ERROR)
            return None

        data = form.cleaned_data
        try:
            locked = availability.adjust_quantities(
                product,
                delta_available=data["delta_available"],
                delta_damaged=data["delta_damaged"],
                delta_lost=data["delta_lost"],
                reason=data["reason"],
                actor=request.user,
            )
        except availability.InsufficientStock as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
        else:
            self.message_user(
                request,
                (
                    f"Updated quantities for {locked}: available="
                    f"{locked.available_quantity}, damaged={locked.damaged_quantity}, "
                    f"lost={locked.lost_quantity}."
                ),
                level=messages.SUCCESS,
            )
        return None


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
