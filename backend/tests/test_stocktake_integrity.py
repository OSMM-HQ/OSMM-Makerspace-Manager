import pytest
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.inventory.models import InventoryAsset, TrackingMode
from apps.operations import services
from apps.operations.models import StocktakeLedgerEntry, StocktakeLine, StocktakeSession
from tests.return_helpers import authenticated_client, make_member, make_product, make_space, make_user

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
