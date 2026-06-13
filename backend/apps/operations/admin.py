from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from apps.operations.models import (
    InventoryAdjustment,
    QrPrintBatch,
    QrPrintBatchItem,
    StockTransfer,
    StockTransferLine,
    StocktakeLine,
    StocktakeSession,
)


class StockTransferLineInline(TabularInline):
    model = StockTransferLine
    extra = 0


@admin.register(StockTransfer)
class StockTransferAdmin(ModelAdmin):
    list_display = ("id", "makerspace", "source_container", "destination_container", "status", "created_at")
    list_filter = ("status", "makerspace")
    inlines = (StockTransferLineInline,)


class StocktakeLineInline(TabularInline):
    model = StocktakeLine
    extra = 0


@admin.register(StocktakeSession)
class StocktakeSessionAdmin(ModelAdmin):
    list_display = ("id", "makerspace", "container", "status", "started_at", "approved_at")
    list_filter = ("status", "makerspace")
    inlines = (StocktakeLineInline,)


@admin.register(InventoryAdjustment)
class InventoryAdjustmentAdmin(ModelAdmin):
    list_display = ("id", "makerspace", "product", "asset", "delta_available", "delta_damaged", "delta_lost", "created_at")
    list_filter = ("makerspace",)


class QrPrintBatchItemInline(TabularInline):
    model = QrPrintBatchItem
    extra = 0


@admin.register(QrPrintBatch)
class QrPrintBatchAdmin(ModelAdmin):
    list_display = ("id", "makerspace", "title", "status", "created_at", "printed_at")
    list_filter = ("status", "makerspace")
    inlines = (QrPrintBatchItemInline,)
