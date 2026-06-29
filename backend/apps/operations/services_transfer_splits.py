from rest_framework.exceptions import ValidationError

from apps.inventory import availability
from apps.inventory.models import InventoryProduct, TrackingMode


def move_quantity_stock(source_product, destination_container, quantity):
    if source_product.tracking_mode == TrackingMode.INDIVIDUAL:
        raise ValidationError(
            {"product_id": "Individual-tracked products must be moved by asset."}
        )
    if quantity > source_product.available_quantity:
        raise ValidationError(
            {"quantity": "Cannot transfer more than the available stock."}
        )

    destination_product = _destination_product(source_product, destination_container)
    if _can_move_source_row(source_product, destination_product, quantity):
        source_product.box = destination_container
        source_product.save(update_fields=["box", "updated_at"])
        return source_product, False

    if destination_product is None:
        destination_product = _create_destination_product(
            source_product,
            destination_container,
        )

    source_product, destination_product = availability.transfer_available_quantity(
        source_product,
        destination_product,
        quantity,
    )
    return destination_product, True


def _can_move_source_row(source_product, destination_product, quantity):
    return (
        destination_product is None
        and quantity == source_product.available_quantity
        and source_product.total_quantity == source_product.available_quantity
        and source_product.reserved_quantity == 0
        and source_product.issued_quantity == 0
        and source_product.damaged_quantity == 0
        and source_product.lost_quantity == 0
        and source_product.needs_fix_quantity == 0
    )


def _destination_product(source_product, destination_container):
    queryset = InventoryProduct.objects.select_for_update().filter(
        makerspace=source_product.makerspace,
        box=destination_container,
        name__iexact=source_product.name,
        tracking_mode=TrackingMode.QUANTITY,
        is_archived=False,
    )
    if source_product.category_id:
        queryset = queryset.filter(category_id=source_product.category_id)
    else:
        queryset = queryset.filter(category__isnull=True)
    return queryset.exclude(pk=source_product.pk).first()


def _create_destination_product(source_product, destination_container):
    return InventoryProduct.objects.create(
        makerspace=source_product.makerspace,
        box=destination_container,
        category=source_product.category,
        name=source_product.name,
        description=source_product.description,
        tracking_mode=TrackingMode.QUANTITY,
        total_quantity=0,
        available_quantity=0,
        storage_location=source_product.storage_location,
        is_public=False,
        public_self_checkout_enabled=False,
        show_public_count=False,
        public_availability_mode=source_product.public_availability_mode,
    )
