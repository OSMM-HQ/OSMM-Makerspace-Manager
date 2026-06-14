import io
import zipfile

import pytest

from apps.accounts.models import User
from apps.boxes.models import Box, QrCode
from apps.inventory.models import InventoryAsset, InventoryProduct, TrackingMode
from apps.operations.models import InventoryAdjustment, QrPrintBatch, StockTransfer, StocktakeSession
from tests.return_helpers import authenticated_client, make_box, make_member, make_product, make_space, make_user

pytestmark = pytest.mark.django_db


def _cross_transfer(superadmin, source, dest, product, quantity):
    return authenticated_client(superadmin).post(
        f"/api/v1/admin/makerspace/{source.id}/stock-transfers",
        {
            "destination_makerspace_id": dest.id,
            "reason": "Lend to partner space",
            "lines": [{"product_id": product.id, "quantity": quantity}],
        },
        format="json",
    )


def test_cross_makerspace_transfer_moves_quantity_to_destination_product():
    source = make_space("xfer-src")
    dest = make_space("xfer-dst")
    superadmin = make_user("xfer-super", role=User.Role.SUPERADMIN, access_status=User.AccessStatus.ACTIVE)
    product = make_product(source, name="Soldering Iron", total_quantity=10, available_quantity=10)

    created = _cross_transfer(superadmin, source, dest, product, 4)

    assert created.status_code == 201
    product.refresh_from_db()
    assert product.available_quantity == 6 and product.total_quantity == 6
    moved = InventoryProduct.objects.get(makerspace=dest, name="Soldering Iron")
    assert moved.available_quantity == 4 and moved.total_quantity == 4
    assert moved.is_public is False  # destination opts in explicitly
    assert InventoryAdjustment.objects.filter(makerspace=source, delta_available=-4).exists()
    assert InventoryAdjustment.objects.filter(makerspace=dest, delta_available=4).exists()


def test_cross_makerspace_transfer_rejects_more_than_available():
    source = make_space("xfer-src2")
    dest = make_space("xfer-dst2")
    superadmin = make_user("xfer-super2", role=User.Role.SUPERADMIN, access_status=User.AccessStatus.ACTIVE)
    product = make_product(source, name="Caliper", total_quantity=3, available_quantity=3)

    response = _cross_transfer(superadmin, source, dest, product, 5)

    assert response.status_code == 400
    product.refresh_from_db()
    assert product.available_quantity == 3  # unchanged


def test_cross_makerspace_transfer_credits_existing_destination_product():
    source = make_space("xfer-src3")
    dest = make_space("xfer-dst3")
    superadmin = make_user("xfer-super3", role=User.Role.SUPERADMIN, access_status=User.AccessStatus.ACTIVE)
    product = make_product(source, name="Multimeter", total_quantity=10, available_quantity=10)
    existing = make_product(dest, name="Multimeter", total_quantity=2, available_quantity=2, is_public=False)

    created = _cross_transfer(superadmin, source, dest, product, 3)

    assert created.status_code == 201
    existing.refresh_from_db()
    assert existing.available_quantity == 5 and existing.total_quantity == 5
    # no duplicate product created in the destination
    assert InventoryProduct.objects.filter(makerspace=dest, name="Multimeter").count() == 1


def test_cross_makerspace_transfer_rejects_individual_destination_match():
    source = make_space("xfer-src5")
    dest = make_space("xfer-dst5")
    superadmin = make_user("xfer-super5", role=User.Role.SUPERADMIN, access_status=User.AccessStatus.ACTIVE)
    product = make_product(source, name="Drill", total_quantity=10, available_quantity=10)
    make_product(dest, name="Drill", total_quantity=1, available_quantity=1, tracking_mode=TrackingMode.INDIVIDUAL)

    response = _cross_transfer(superadmin, source, dest, product, 2)

    assert response.status_code == 400
    product.refresh_from_db()
    assert product.available_quantity == 10  # source untouched


def test_cross_makerspace_transfer_rejects_individual_tracking():
    source = make_space("xfer-src4")
    dest = make_space("xfer-dst4")
    superadmin = make_user("xfer-super4", role=User.Role.SUPERADMIN, access_status=User.AccessStatus.ACTIVE)
    product = make_product(
        source, name="Arduino", total_quantity=5, available_quantity=5, tracking_mode=TrackingMode.INDIVIDUAL
    )

    response = _cross_transfer(superadmin, source, dest, product, 1)

    assert response.status_code == 400


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


def test_asset_generation_adds_50_unique_sequential_unit_qrs_to_existing_batch():
    makerspace = make_space("ops-assets-50")
    manager = make_member("ops-assets-50-manager", makerspace)
    product = make_product(makerspace, name="Arduino", tracking_mode=TrackingMode.INDIVIDUAL)
    batch = QrPrintBatch.objects.create(makerspace=makerspace, title="Arduino labels", created_by=manager)

    response = authenticated_client(manager).post(
        f"/api/v1/admin/products/{product.id}/assets/generate",
        {"count": 50, "name_prefix": "Arduino", "print_batch_id": batch.id},
        format="json",
    )

    assert response.status_code == 201
    assert len(response.data["assets"]) == 50
    assert InventoryAsset.objects.filter(product=product).count() == 50
    assert QrCode.objects.filter(target_type=QrCode.TargetType.ASSET).count() == 50
    assert QrCode.objects.filter(target_type=QrCode.TargetType.ASSET).values("payload").distinct().count() == 50
    assert list(batch.items.order_by("sort_order").values_list("label_text", flat=True)) == [
        f"Arduino {number}" for number in range(1, 51)
    ]


def test_qr_batch_accepts_box_and_product_items_and_downloads_name_captions():
    makerspace = make_space("ops-qr-batch")
    manager = make_member("ops-qr-batch-manager", makerspace)
    box = make_box(makerspace, "Soldering Bin")
    product = make_product(makerspace, name="Multimeter")
    box_qr = QrCode.objects.create(
        makerspace=makerspace,
        payload=box.code,
        target_type=QrCode.TargetType.BOX,
        target_id=box.id,
        created_by=manager,
    )
    product_qr = QrCode.objects.create(
        makerspace=makerspace,
        target_type=QrCode.TargetType.PRODUCT,
        target_id=product.id,
        created_by=manager,
    )
    client = authenticated_client(manager)
    batch_response = client.post(
        f"/api/v1/admin/makerspace/{makerspace.id}/qr-print-batches",
        {"title": "Bench labels"},
        format="json",
    )
    batch_id = batch_response.data["id"]

    box_item = client.post(
        f"/api/v1/admin/qr-print-batches/{batch_id}/items",
        {"qr_code_id": box_qr.id, "label_text": box.label},
        format="json",
    )
    product_item = client.post(
        f"/api/v1/admin/qr-print-batches/{batch_id}/items",
        {"qr_code_id": product_qr.id, "label_text": product.name},
        format="json",
    )
    downloaded = client.get(f"/api/v1/admin/qr-print-batches/{batch_id}/download")

    assert batch_response.status_code == 201
    assert box_item.status_code == 201
    assert product_item.status_code == 201
    assert downloaded.status_code == 200
    assert downloaded["Content-Type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
        assert len(archive.namelist()) == 2
        svg_contents = "".join(archive.read(name).decode("utf-8") for name in archive.namelist())
    assert "Soldering Bin" in svg_contents
    assert "Multimeter" in svg_contents


def test_qr_batch_items_enforce_manage_qr_rbac_and_makerspace_scope():
    space_a = make_space("ops-qr-scope-a")
    space_b = make_space("ops-qr-scope-b")
    manager_a = make_member("ops-qr-scope-manager-a", space_a)
    guest_a = make_member("ops-qr-scope-guest-a", space_a, membership_role="guest_admin", role="guest_admin")
    box_b = make_box(space_b, "Foreign Bin")
    qr_b = QrCode.objects.create(
        makerspace=space_b,
        payload=box_b.code,
        target_type=QrCode.TargetType.BOX,
        target_id=box_b.id,
    )
    batch_b = QrPrintBatch.objects.create(makerspace=space_b, title="Foreign labels")

    denied_role = authenticated_client(guest_a).post(
        f"/api/v1/admin/makerspace/{space_a.id}/qr-print-batches",
        {"title": "Denied"},
        format="json",
    )
    denied_scope = authenticated_client(manager_a).post(
        f"/api/v1/admin/qr-print-batches/{batch_b.id}/items",
        {"qr_code_id": qr_b.id},
        format="json",
    )

    assert denied_role.status_code == 403
    assert denied_scope.status_code == 404
