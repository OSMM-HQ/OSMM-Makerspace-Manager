import pytest
from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.inventory.models import InventoryAsset, TrackingMode
from apps.operations import services
from apps.operations.models import StocktakeLedgerEntry, StocktakeLine, StocktakeSession
from tests.return_helpers import authenticated_client, make_box, make_member, make_product, make_space, make_user

pytestmark = pytest.mark.django_db


def test_stocktake_apply_rejects_foreign_product_line():
    makerspace = make_space("stocktake-scope-owner")
    foreign = make_space("stocktake-scope-foreign")
    actor = make_user(
        "stocktake-scope-super",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )
    product = make_product(foreign, name="Foreign meter", available_quantity=5, total_quantity=5)
    stocktake = StocktakeSession.objects.create(
        makerspace=makerspace,
        started_by=actor,
        status=StocktakeSession.Status.APPROVED,
    )
    StocktakeLine.objects.create(
        stocktake=stocktake,
        product=product,
        expected_quantity=5,
        counted_quantity=0,
        variance_quantity=-5,
    )

    with pytest.raises(ValidationError):
        services.apply_stocktake_adjustments(actor, stocktake)

    product.refresh_from_db()
    stocktake.refresh_from_db()
    assert (product.available_quantity, product.total_quantity) == (5, 5)
    assert stocktake.status == StocktakeSession.Status.APPROVED
    assert StocktakeLedgerEntry.objects.count() == 0


def test_stocktake_rejects_issued_asset_count_before_line_create():
    makerspace = make_space("stocktake-issued-asset")
    manager = make_member(
        "stocktake-issued-asset-manager",
        makerspace,
        membership_role="inventory_manager",
        role=User.Role.REQUESTER,
    )
    product = make_product(
        makerspace,
        tracking_mode=TrackingMode.INDIVIDUAL,
        total_quantity=1,
        available_quantity=0,
        issued_quantity=1,
    )
    asset = InventoryAsset.objects.create(
        makerspace=makerspace,
        product=product,
        asset_tag="ISSUED-ASSET-1",
        status=InventoryAsset.Status.ISSUED,
    )
    stocktake = StocktakeSession.objects.create(makerspace=makerspace, started_by=manager)

    response = authenticated_client(manager).post(
        f"/api/v1/admin/stocktakes/{stocktake.id}/count-lines",
        {"asset_id": asset.id, "counted_quantity": 1, "condition": "available"},
        format="json",
    )

    assert response.status_code == 400
    assert StocktakeLine.objects.count() == 0
    product.refresh_from_db()
    assert (product.available_quantity, product.issued_quantity, product.total_quantity) == (0, 1, 1)


def test_stocktake_apply_rejects_stale_product_expected_quantity():
    makerspace = make_space("stocktake-stale")
    actor = make_user(
        "stocktake-stale-super",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )
    product = make_product(makerspace, name="Shared Meter", total_quantity=5, available_quantity=5)
    stocktake = StocktakeSession.objects.create(
        makerspace=makerspace,
        started_by=actor,
        status=StocktakeSession.Status.APPROVED,
    )
    StocktakeLine.objects.create(
        stocktake=stocktake,
        product=product,
        expected_quantity=5,
        counted_quantity=4,
        variance_quantity=-1,
        condition=StocktakeLine.Condition.AVAILABLE,
    )
    product.available_quantity = 3
    product.save(update_fields=["available_quantity", "updated_at"])

    with pytest.raises(ValidationError, match="stale"):
        services.apply_stocktake_adjustments(actor, stocktake)

    product.refresh_from_db()
    stocktake.refresh_from_db()
    assert product.available_quantity == 3
    assert stocktake.status == StocktakeSession.Status.APPROVED
    assert StocktakeLedgerEntry.objects.count() == 0


def test_stocktake_duplicate_product_line_constraint_handles_null_container():
    makerspace = make_space("stocktake-duplicate-product")
    actor = make_user("stocktake-duplicate-product-super", role=User.Role.SUPERADMIN)
    product = make_product(makerspace, name="Clamp", total_quantity=2, available_quantity=2)
    stocktake = StocktakeSession.objects.create(makerspace=makerspace, started_by=actor)
    StocktakeLine.objects.create(
        stocktake=stocktake,
        product=product,
        expected_quantity=2,
        counted_quantity=2,
        condition=StocktakeLine.Condition.AVAILABLE,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            StocktakeLine.objects.create(
                stocktake=stocktake,
                product=product,
                expected_quantity=2,
                counted_quantity=1,
                condition=StocktakeLine.Condition.AVAILABLE,
            )


def test_stocktake_duplicate_asset_line_constraint():
    makerspace = make_space("stocktake-duplicate-asset")
    actor = make_user("stocktake-duplicate-asset-super", role=User.Role.SUPERADMIN)
    product = make_product(
        makerspace,
        tracking_mode=TrackingMode.INDIVIDUAL,
        total_quantity=1,
        available_quantity=1,
    )
    asset = InventoryAsset.objects.create(
        makerspace=makerspace,
        product=product,
        asset_tag="DUP-ASSET-1",
        status=InventoryAsset.Status.AVAILABLE,
    )
    stocktake = StocktakeSession.objects.create(makerspace=makerspace, started_by=actor)
    StocktakeLine.objects.create(
        stocktake=stocktake,
        asset=asset,
        expected_quantity=1,
        counted_quantity=1,
        condition=StocktakeLine.Condition.AVAILABLE,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            StocktakeLine.objects.create(
                stocktake=stocktake,
                asset=asset,
                expected_quantity=1,
                counted_quantity=0,
                condition=StocktakeLine.Condition.AVAILABLE,
            )


def test_container_scoped_stocktake_rejects_child_box_at_count_time():
    makerspace = make_space("stocktake-container-count")
    manager = make_member(
        "stocktake-container-count-manager",
        makerspace,
        membership_role="inventory_manager",
        role=User.Role.REQUESTER,
    )
    parent = make_box(makerspace, "Parent Box")
    child = make_box(makerspace, "Child Box")
    child.parent = parent
    child.save(update_fields=["parent", "updated_at"])
    product = make_product(makerspace, name="Nested Meter", box=child)
    stocktake = StocktakeSession.objects.create(
        makerspace=makerspace,
        container=parent,
        started_by=manager,
    )

    response = authenticated_client(manager).post(
        f"/api/v1/admin/stocktakes/{stocktake.id}/count-lines",
        {
            "product_id": product.id,
            "container_id": child.id,
            "counted_quantity": 1,
            "condition": "available",
        },
        format="json",
    )

    assert response.status_code == 400
    assert StocktakeLine.objects.filter(stocktake=stocktake).count() == 0


def test_container_scoped_stocktake_rejects_legacy_child_box_line_at_apply_time():
    makerspace = make_space("stocktake-container-apply")
    actor = make_user(
        "stocktake-container-apply-super",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )
    parent = make_box(makerspace, "Apply Parent")
    child = make_box(makerspace, "Apply Child")
    child.parent = parent
    child.save(update_fields=["parent", "updated_at"])
    product = make_product(makerspace, name="Legacy Nested Meter", box=child)
    stocktake = StocktakeSession.objects.create(
        makerspace=makerspace,
        container=parent,
        started_by=actor,
        status=StocktakeSession.Status.APPROVED,
    )
    StocktakeLine.objects.create(
        stocktake=stocktake,
        product=product,
        container=child,
        expected_quantity=10,
        counted_quantity=9,
        variance_quantity=-1,
        condition=StocktakeLine.Condition.AVAILABLE,
    )

    with pytest.raises(ValidationError, match="container"):
        services.apply_stocktake_adjustments(actor, stocktake)

    stocktake.refresh_from_db()
    assert stocktake.status == StocktakeSession.Status.APPROVED
    assert StocktakeLedgerEntry.objects.count() == 0
