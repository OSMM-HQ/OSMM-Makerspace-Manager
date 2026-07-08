import logging
from decimal import Decimal

from django.db import transaction

from apps.audit import services as audit
from apps.printing.models import FilamentSpool
from apps.procurement.models import ToBuyItem

logger = logging.getLogger(__name__)

OPEN_STATUSES = (
    ToBuyItem.Status.REQUESTED,
    ToBuyItem.Status.APPROVED,
    ToBuyItem.Status.ORDERED,
)


def maybe_flag_low_stock(actor, spool):
    """Create one open printing procurement item when an active spool is low.

    This is deliberately fail-safe: procurement automation must never abort the
    print, manual log, reserve, reconcile, or staff-adjustment flow that consumed
    filament.
    """
    try:
        if not getattr(spool, "pk", None):
            return None
        with transaction.atomic():
            locked_spool = (
                FilamentSpool.objects.select_for_update()
                .select_related("makerspace")
                .get(pk=spool.pk)
            )
            threshold = Decimal(
                locked_spool.makerspace.filament_low_stock_threshold_grams or 0
            )
            if threshold <= 0:
                return None
            if not locked_spool.is_active:
                return None
            remaining = locked_spool.remaining_weight_grams
            if remaining > threshold:
                return None
            if ToBuyItem.objects.filter(
                source_spool=locked_spool,
                kind=ToBuyItem.Kind.PRINTING,
                status__in=OPEN_STATUSES,
            ).exists():
                return None
            created_by = actor if getattr(actor, "is_authenticated", False) else None
            item = ToBuyItem.objects.create(
                makerspace=locked_spool.makerspace,
                kind=ToBuyItem.Kind.PRINTING,
                name=f"Filament restock: {locked_spool.material} {locked_spool.color}".strip(),
                quantity=1,
                source_spool=locked_spool,
                created_by=created_by,
                status=ToBuyItem.Status.REQUESTED,
            )
            audit.record(
                actor if getattr(actor, "is_authenticated", False) else None,
                "procurement.low_stock_flagged",
                makerspace=locked_spool.makerspace,
                target=item,
                meta={
                    "spool_id": locked_spool.id,
                    "remaining": str(remaining),
                    "threshold": str(threshold),
                    "to_buy_item_id": item.id,
                },
            )
            return item
    except Exception:
        logger.exception(
            "Failed to flag low-stock filament spool %s",
            getattr(spool, "pk", None),
        )
        return None