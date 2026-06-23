import pytest

from apps.inventory.models import InventoryProduct
from tests.return_helpers import authenticated_client, make_member, make_product, make_space

pytestmark = pytest.mark.django_db


def test_inventory_patch_rejects_direct_bucket_fields():
    makerspace = make_space("bucket-patch")
    admin = make_member("bucket-patch-admin", makerspace)
    product = make_product(
        makerspace,
        name="Scope Meter",
        total_quantity=5,
        available_quantity=5,
    )

    response = authenticated_client(admin).patch(
        f"/api/v1/admin/inventory/{product.id}",
        {"available_quantity": 99, "name": "Tampered Meter"},
        format="json",
    )

    assert response.status_code == 400
    assert "available_quantity" in response.data
    product.refresh_from_db()
    assert product.available_quantity == 5
    assert product.name == "Scope Meter"


def test_inventory_create_seeds_initial_total_and_available_quantities():
    makerspace = make_space("bucket-create")
    admin = make_member("bucket-create-admin", makerspace)

    response = authenticated_client(admin).post(
        f"/api/v1/admin/makerspace/{makerspace.id}/inventory",
        {
            "name": "Bench Supply",
            "tracking_mode": "quantity",
            "total_quantity": 4,
            "available_quantity": 3,
        },
        format="json",
    )

    assert response.status_code == 201
    product = InventoryProduct.objects.get(makerspace=makerspace, name="Bench Supply")
    assert product.total_quantity == 4
    assert product.available_quantity == 3
    assert product.reserved_quantity == 0
    assert product.issued_quantity == 0


def test_bulk_import_update_does_not_overwrite_existing_quantity_buckets():
    makerspace = make_space("bucket-bulk-update")
    admin = make_member("bucket-bulk-update-admin", makerspace)
    product = make_product(
        makerspace,
        name="Calipers",
        total_quantity=10,
        available_quantity=7,
        reserved_quantity=1,
        issued_quantity=2,
        description="Old description",
    )

    response = authenticated_client(admin).post(
        f"/api/v1/admin/makerspace/{makerspace.id}/inventory/import/apply",
        {
            "rows": [
                {
                    "name": "Calipers",
                    "description": "Updated description",
                    "total_quantity": "1",
                    "available_quantity": "1",
                    "reserved_quantity": "0",
                    "issued_quantity": "0",
                }
            ]
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["updated"] == 1
    product.refresh_from_db()
    assert product.description == "Updated description"
    assert product.total_quantity == 10
    assert product.available_quantity == 7
    assert product.reserved_quantity == 1
    assert product.issued_quantity == 2


def test_bulk_import_create_can_seed_quantity_buckets():
    makerspace = make_space("bucket-bulk-create")
    admin = make_member("bucket-bulk-create-admin", makerspace)

    response = authenticated_client(admin).post(
        f"/api/v1/admin/makerspace/{makerspace.id}/inventory/import/apply",
        {
            "rows": [
                {
                    "name": "Loan Kit",
                    "total_quantity": "6",
                    "available_quantity": "2",
                    "reserved_quantity": "1",
                    "issued_quantity": "1",
                    "damaged_quantity": "1",
                    "lost_quantity": "1",
                }
            ]
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["created"] == 1
    product = InventoryProduct.objects.get(makerspace=makerspace, name="Loan Kit")
    assert product.total_quantity == 6
    assert product.available_quantity == 2
    assert product.reserved_quantity == 1
    assert product.issued_quantity == 1
    assert product.damaged_quantity == 1
    assert product.lost_quantity == 1