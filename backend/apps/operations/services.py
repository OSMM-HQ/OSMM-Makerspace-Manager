from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit
from apps.boxes.models import Box, QrCode
from apps.inventory.models import InventoryAsset, InventoryProduct, TrackingMode
from apps.operations.models import (
    InventoryAdjustment,
    QrPrintBatch,
    QrPrintBatchItem,
    StockTransfer,
    StockTransferLine,
    StocktakeLine,
    StocktakeSession,
)
from apps.operations.services_qr_assets import (
    _target_label,
    add_qr_to_batch,
    generate_assets_with_qr,
    mark_batch_printed,
)
from apps.operations.services_shared import _container
from apps.operations.services_stocktake import (
    add_stocktake_line,
    apply_stocktake_adjustments,
    approve_stocktake,
    complete_stocktake,
    create_stocktake,
    resolve_scan_target,
)
from apps.operations.services_transfers import (
    _apply_cross_makerspace_line,
    _apply_intra_makerspace_line,
    apply_stock_transfer,
)
