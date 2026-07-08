import pytest

from apps.accounts.models import User
from apps.boxes.models import Box
from apps.inventory.models import Category, InventoryProduct
from apps.makerspaces.models import MakerspaceMembership
from apps.operations.models import InventoryAdjustment
from apps.printing.models import FilamentSpool
from apps.procurement.models import ToBuyItem
from tests.test_printing import authenticated_client, make_member, make_print_manager, make_space, make_user

pytestmark = pytest.mark.django_db


def make_inventory_manager(username, makerspace):
    return make_member(
        username,
        makerspace,
        membership_role=MakerspaceMembership.Role.INVENTORY_MANAGER,
        role=User.Role.REQUESTER,
    )


def make_space_manager(username, makerspace):
    return make_member(
        username,
        makerspace,
        membership_role=MakerspaceMembership.Role.SPACE_MANAGER,
        role=User.Role.SPACE_MANAGER,
    )


def make_superadmin(username):
    return make_user(
        username,
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )


def move_inventory_url(item):
    return f"/api/v1/procurement/to-buy/{item.id}/move-to-inventory"


def move_printing_url(item):
    return f"/api/v1/procurement/to-buy/{item.id}/move-to-printing"


def received_item(space, *, kind=ToBuyItem.Kind.HARDWARE, name="Procured item", quantity=4):
    return ToBuyItem.objects.create(
        makerspace=space,
        kind=kind,
        name=name,
        quantity=quantity,
        status=ToBuyItem.Status.RECEIVED,
    )


def product(space, **overrides):
    data = {
        "makerspace": space,
        "name": "Existing drill",
        "total_quantity": 2,
        "available_quantity": 2,
        "is_public": True,
    }
    data.update(overrides)
    return InventoryProduct.objects.create(**data)


def create_payload(**overrides):
    data = {
        "mode": "create",
        "quantity": 3,
        "name": "Soldering iron",
        "description": "Fine tip",
        "tracking_mode": "quantity",
        "is_public": False,
        "public_availability_mode": "hidden",
        "show_public_count": False,
        "public_self_checkout_enabled": False,
    }
    data.update(overrides)
    return data


def test_move_to_inventory_create_new_product_uses_adjustment_and_stamps_item():
    space = make_space("move-inv-create")
    actor = make_inventory_manager("move-inv-create-user", space)
    item = received_item(space, quantity=3)

    response = authenticated_client(actor).post(
        move_inventory_url(item),
        create_payload(quantity=3, is_public=False),
        format="json",
    )

    assert response.status_code == 200
    item.refresh_from_db()
    created = InventoryProduct.objects.get(pk=response.data["resulting_product"])
    assert item.moved_to_inventory_at is not None
    assert item.resulting_product == created
    assert created.makerspace == space
    assert created.name == "Soldering iron"
    assert created.available_quantity == 3
    assert created.total_quantity == 3
    assert created.is_public is False
    assert InventoryAdjustment.objects.filter(
        product=created,
        delta_available=3,
        reason=f"Received from to-buy #{item.id}",
        created_by=actor,
    ).count() == 1


def test_move_to_inventory_topup_existing_product_records_adjustment():
    space = make_space("move-inv-topup")
    actor = make_inventory_manager("move-inv-topup-user", space)
    item = received_item(space, quantity=5)
    existing = product(space, available_quantity=2, total_quantity=2)

    response = authenticated_client(actor).post(
        move_inventory_url(item),
        {"mode": "topup", "product_id": existing.id, "quantity": 4},
        format="json",
    )

    assert response.status_code == 200
    existing.refresh_from_db()
    item.refresh_from_db()
    assert response.data["resulting_product"] == existing.id
    assert item.resulting_product_id == existing.id
    assert existing.available_quantity == 6
    assert existing.total_quantity == 6
    assert InventoryAdjustment.objects.filter(product=existing, delta_available=4).count() == 1


def test_move_to_inventory_create_applies_box_category_and_visibility():
    space = make_space("move-inv-visibility")
    actor = make_inventory_manager("move-inv-visibility-user", space)
    item = received_item(space)
    box = Box.objects.create(makerspace=space, label="Received shelf")
    category = Category.objects.create(makerspace=space, name="Tools", slug="tools")

    response = authenticated_client(actor).post(
        move_inventory_url(item),
        create_payload(
            box=box.id,
            category=category.id,
            is_public=True,
            public_availability_mode="exact_count",
            show_public_count=True,
            public_self_checkout_enabled=True,
        ),
        format="json",
    )

    assert response.status_code == 200
    created = InventoryProduct.objects.get(pk=response.data["resulting_product"])
    assert created.box == box
    assert created.category == category
    assert created.is_public is True
    assert created.public_availability_mode == "exact_count"
    assert created.show_public_count is True
    assert created.public_self_checkout_enabled is True


def test_move_to_inventory_rejects_double_move_without_second_adjustment():
    space = make_space("move-inv-double")
    actor = make_inventory_manager("move-inv-double-user", space)
    item = received_item(space)
    client = authenticated_client(actor)

    first = client.post(move_inventory_url(item), create_payload(quantity=2), format="json")
    second = client.post(move_inventory_url(item), create_payload(quantity=2), format="json")

    assert first.status_code == 200
    assert second.status_code in (400, 409)
    assert InventoryAdjustment.objects.count() == 1
    item.refresh_from_db()
    assert item.resulting_product_id == first.data["resulting_product"]


def test_move_to_inventory_rejects_cross_makerspace_box():
    space = make_space("move-inv-box-a")
    other = make_space("move-inv-box-b")
    actor = make_inventory_manager("move-inv-box-user", space)
    item = received_item(space)
    foreign_box = Box.objects.create(makerspace=other, label="Foreign shelf")

    response = authenticated_client(actor).post(
        move_inventory_url(item),
        create_payload(box=foreign_box.id),
        format="json",
    )

    assert response.status_code == 400
    assert "box" in response.data
    assert InventoryProduct.objects.count() == 0
    assert InventoryAdjustment.objects.count() == 0


def test_move_to_inventory_rejects_non_received_item():
    space = make_space("move-inv-status")
    actor = make_inventory_manager("move-inv-status-user", space)
    item = ToBuyItem.objects.create(
        makerspace=space,
        kind=ToBuyItem.Kind.HARDWARE,
        name="Pending item",
        status=ToBuyItem.Status.ORDERED,
    )

    response = authenticated_client(actor).post(
        move_inventory_url(item),
        create_payload(),
        format="json",
    )

    assert response.status_code == 400
    assert InventoryProduct.objects.count() == 0
    assert InventoryAdjustment.objects.count() == 0


def test_move_to_inventory_topup_cross_tenant_product_is_404():
    space = make_space("move-inv-product-a")
    other = make_space("move-inv-product-b")
    actor = make_inventory_manager("move-inv-product-user", space)
    item = received_item(space)
    foreign_product = product(other)

    response = authenticated_client(actor).post(
        move_inventory_url(item),
        {"mode": "topup", "product_id": foreign_product.id, "quantity": 1},
        format="json",
    )

    assert response.status_code == 404
    assert InventoryAdjustment.objects.count() == 0


def test_stream_rbac_blocks_wrong_managers():
    space = make_space("move-rbac")
    print_manager = make_print_manager("move-rbac-print", space)
    inventory_manager = make_inventory_manager("move-rbac-inventory", space)
    hardware_item = received_item(space, kind=ToBuyItem.Kind.HARDWARE, name="Hardware")
    printing_item = received_item(space, kind=ToBuyItem.Kind.PRINTING, name="Printing")

    hardware_response = authenticated_client(print_manager).post(
        move_inventory_url(hardware_item),
        create_payload(),
        format="json",
    )
    printing_response = authenticated_client(inventory_manager).post(
        move_printing_url(printing_item),
        {
            "target": "spool",
            "material": "PLA",
            "initial_weight_grams": "1000.00",
            "remaining_weight_grams": "1000.00",
        },
        format="json",
    )

    assert hardware_response.status_code == 404
    assert printing_response.status_code == 404


def test_move_to_printing_spool_happy_path_and_idempotency():
    space = make_space("move-print-spool")
    actor = make_print_manager("move-print-spool-user", space)
    item = received_item(space, kind=ToBuyItem.Kind.PRINTING, name="PLA spool")
    client = authenticated_client(actor)

    first = client.post(
        move_printing_url(item),
        {
            "target": "spool",
            "material": "PLA",
            "color": "Black",
            "brand": "MakerFil",
            "initial_weight_grams": "1000.00",
            "remaining_weight_grams": "1000.00",
            "is_active": True,
        },
        format="json",
    )
    second = client.post(
        move_printing_url(item),
        {
            "target": "spool",
            "material": "PLA",
            "initial_weight_grams": "1000.00",
            "remaining_weight_grams": "1000.00",
        },
        format="json",
    )

    assert first.status_code == 200
    assert second.status_code in (400, 409)
    item.refresh_from_db()
    spool = FilamentSpool.objects.get(pk=first.data["resulting_spool"])
    assert item.moved_to_inventory_at is not None
    assert item.resulting_spool == spool
    assert spool.makerspace == space
    assert spool.material == "PLA"
    assert spool.color == "Black"
    assert FilamentSpool.objects.count() == 1


def test_space_manager_can_move_printing_printer():
    space = make_space("move-print-printer")
    actor = make_space_manager("move-print-printer-user", space)
    item = received_item(space, kind=ToBuyItem.Kind.PRINTING, name="Printer")

    response = authenticated_client(actor).post(
        move_printing_url(item),
        {"target": "printer", "name": "Prusa MK4", "model": "MK4", "status": "active"},
        format="json",
    )

    assert response.status_code == 200
    item.refresh_from_db()
    assert item.resulting_printer_id == response.data["resulting_printer"]
