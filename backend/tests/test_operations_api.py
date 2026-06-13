import pytest

from apps.accounts.models import User
from apps.boxes.models import Box, QrCode
from apps.inventory.models import TrackingMode
from apps.operations.models import QrPrintBatch, StockTransfer, StocktakeSession
from tests.return_helpers import authenticated_client, make_box, make_member, make_product, make_space, make_user

pytestmark = pytest.mark.django_db


def test_stock_transfer_is_superadmin_only_and_moves_product_container():
    makerspace = make_space("ops-transfer")
    manager = make_member("ops-transfer-manager", makerspace)
    superadmin = make_user("ops-transfer-super", role=User.Role.SUPERADMIN, access_status=User.AccessStatus.ACTIVE)
    product = make_product(makerspace)
    destination = make_box(makerspace, "Destination")
    payload = {
        "destination_container_id": destination.id,
        "reason": "Move to shelf",
        "lines": [{"product_id": product.id, "quantity": 1}],
    }

    denied = authenticated_client(manager).post(
        f"/api/v1/admin/makerspace/{makerspace.id}/stock-transfers",
        payload,
        format="json",
    )
    created = authenticated_client(superadmin).post(
        f"/api/v1/admin/makerspace/{makerspace.id}/stock-transfers",
        payload,
        format="json",
    )

    assert denied.status_code == 403
    assert created.status_code == 201
    product.refresh_from_db()
    assert product.box_id == destination.id
    assert StockTransfer.objects.count() == 1


def test_stocktake_lifecycle_applies_superadmin_adjustment():
    makerspace = make_space("ops-stocktake")
    manager = make_member("ops-stocktake-manager", makerspace, membership_role="inventory_manager", role=User.Role.REQUESTER)
    superadmin = make_user("ops-stocktake-super", role=User.Role.SUPERADMIN, access_status=User.AccessStatus.ACTIVE)
    product = make_product(makerspace, available_quantity=10, total_quantity=10)
    manager_client = authenticated_client(manager)
    super_client = authenticated_client(superadmin)

    created = manager_client.post(
        f"/api/v1/admin/makerspace/{makerspace.id}/stocktakes",
        {"notes": "Cycle count"},
        format="json",
    )
    stocktake_id = created.data["id"]
    counted = manager_client.post(
        f"/api/v1/admin/stocktakes/{stocktake_id}/count-lines",
        {"product_id": product.id, "counted_quantity": 8, "condition": "available"},
        format="json",
    )
    completed = manager_client.post(f"/api/v1/admin/stocktakes/{stocktake_id}/complete")
    approved = super_client.post(f"/api/v1/admin/stocktakes/{stocktake_id}/approve")
    applied = super_client.post(f"/api/v1/admin/stocktakes/{stocktake_id}/apply-adjustments")

    assert created.status_code == 201
    assert counted.status_code == 201
    assert counted.data["variance_quantity"] == -2
    assert completed.status_code == 200
    assert approved.status_code == 200
    assert applied.status_code == 200
    product.refresh_from_db()
    assert product.available_quantity == 8
    assert StocktakeSession.objects.get(pk=stocktake_id).status == StocktakeSession.Status.APPLIED


def test_reports_export_csv_and_xlsx():
    makerspace = make_space("ops-reports")
    manager = make_member("ops-reports-manager", makerspace)
    make_product(
        makerspace,
        name="Meters",
        total_quantity=13,
        available_quantity=10,
        damaged_quantity=1,
        lost_quantity=2,
    )
    client = authenticated_client(manager)

    csv_response = client.get(
        f"/api/v1/admin/makerspace/{makerspace.id}/reports/damaged-missing/export?format=csv"
    )
    xlsx_response = client.get(
        f"/api/v1/admin/makerspace/{makerspace.id}/reports/damaged-missing/export?format=xlsx"
    )

    assert csv_response.status_code == 200
    assert b"damaged_quantity" in csv_response.content
    assert xlsx_response.status_code == 200
    assert xlsx_response["Content-Type"].startswith("application/vnd.openxmlformats")


def test_asset_generation_creates_qr_labels_in_print_batch():
    makerspace = make_space("ops-assets")
    manager = make_member("ops-assets-manager", makerspace)
    product = make_product(makerspace, name="Drill", tracking_mode=TrackingMode.INDIVIDUAL)

    response = authenticated_client(manager).post(
        f"/api/v1/admin/products/{product.id}/assets/generate",
        {"count": 2, "create_print_batch": True},
        format="json",
    )

    assert response.status_code == 201
    assert len(response.data["assets"]) == 2
    assert QrCode.objects.filter(target_type=QrCode.TargetType.ASSET).count() == 2
    assert QrPrintBatch.objects.get(pk=response.data["print_batch_id"]).items.count() == 2
