from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from rest_framework.exceptions import ValidationError as DRFValidationError
from unfold.admin import ModelAdmin, TabularInline

from apps.operations import services
from apps.operations.models import (
    InventoryAdjustment,
    QrPrintBatch,
    QrPrintBatchItem,
    StockTransfer,
    StockTransferLine,
    StocktakeLine,
    StocktakeSession,
)
from apps.operations.qr_zip import build_batch_zip
from config.admin_access import SuperuserOnlyModelAdmin


class StockTransferLineInline(TabularInline):
    # Transfer lines are created by services.apply_stock_transfer with the parent transfer.
    model = StockTransferLine
    extra = 0
    can_delete = False
    readonly_fields = ("transfer", "product", "asset", "quantity", "from_status", "to_status", "notes")
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockTransfer)
class StockTransferAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    # Transfers are created by the API/React flow via services.apply_stock_transfer.
    list_display = ("id", "makerspace", "source_container", "destination_container", "status", "created_at")
    list_filter = ("status", "makerspace")
    readonly_fields = (
        "makerspace",
        "source_container",
        "destination_container",
        "source_makerspace",
        "destination_makerspace",
        "created_by",
        "reason",
        "status",
        "created_at",
        "applied_at",
    )
    fields = readonly_fields
    inlines = (StockTransferLineInline,)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class StocktakeLineInline(TabularInline):
    model = StocktakeLine
    extra = 0
    can_delete = False
    readonly_fields = (
        "stocktake",
        "product",
        "asset",
        "container",
        "expected_quantity",
        "counted_quantity",
        "variance_quantity",
        "condition",
        "notes",
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StocktakeSession)
class StocktakeSessionAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    actions = ["complete_selected", "approve_selected", "apply_adjustments_selected"]
    list_display = ("id", "makerspace", "container", "status", "started_at", "approved_at")
    list_filter = ("status", "makerspace")
    inlines = (StocktakeLineInline,)

    @admin.action(description="Complete selected stocktakes")
    def complete_selected(self, request, queryset):
        self._run_stocktake_action(request, queryset, services.complete_stocktake, "Completed")

    @admin.action(description="Approve selected stocktakes")
    def approve_selected(self, request, queryset):
        self._run_stocktake_action(request, queryset, services.approve_stocktake, "Approved")

    @admin.action(description="Apply selected stocktake adjustments")
    def apply_adjustments_selected(self, request, queryset):
        self._run_stocktake_action(request, queryset, services.apply_stocktake_adjustments, "Applied adjustments for")

    def _run_stocktake_action(self, request, queryset, service_func, success_label):
        success_count = 0
        for stocktake in queryset:
            try:
                service_func(request.user, stocktake)
            except (DRFValidationError, DjangoValidationError) as exc:
                self.message_user(request, f"{stocktake.pk}: {exc}", level=messages.ERROR)
            else:
                success_count += 1

        if success_count:
            self.message_user(request, f"{success_label} {success_count} stocktake(s).", level=messages.SUCCESS)


@admin.register(InventoryAdjustment)
class InventoryAdjustmentAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("id", "makerspace", "product", "asset", "delta_available", "delta_damaged", "delta_lost", "created_at")
    list_filter = ("makerspace",)


class QrPrintBatchItemInline(TabularInline):
    model = QrPrintBatchItem
    extra = 0


@admin.register(QrPrintBatch)
class QrPrintBatchAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    actions = ["mark_printed_selected", "download_zip_selected"]
    list_display = ("id", "makerspace", "title", "status", "created_at", "printed_at")
    list_filter = ("status", "makerspace")
    inlines = (QrPrintBatchItemInline,)

    @admin.action(description="Mark selected QR print batches as printed")
    def mark_printed_selected(self, request, queryset):
        success_count = 0
        for batch in queryset:
            try:
                services.mark_batch_printed(request.user, batch)
            except (DRFValidationError, DjangoValidationError) as exc:
                self.message_user(request, f"{batch.pk}: {exc}", level=messages.ERROR)
            else:
                success_count += 1

        if success_count:
            self.message_user(request, f"Marked {success_count} QR print batch(es) as printed.", level=messages.SUCCESS)

    @admin.action(description="Download QR ZIP (select exactly one batch)")
    def download_zip_selected(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Select exactly one batch to download.", level=messages.ERROR)
            return None

        batch = queryset.first()
        resp = HttpResponse(build_batch_zip(batch), content_type="application/zip")
        resp["Content-Disposition"] = f'attachment; filename="qr-batch-{batch.pk}.zip"'
        return resp
