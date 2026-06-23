import pytest

from apps.accounts.models import User
from apps.boxes.models import QrCode
from apps.inventory.models import InventoryAsset
from tests.return_helpers import authenticated_client, make_product, make_space, make_user

pytestmark = pytest.mark.django_db


def _qr(product, actor=None):
    return QrCode.objects.create(
        makerspace=product.makerspace,
        target_type=QrCode.TargetType.PRODUCT,
        target_id=product.id,
        created_by=actor,
    )


def _rebind_payload(product, new_name="Renamed"):
    return {
        "target_type": QrCode.TargetType.PRODUCT,
        "target_id": product.id,
        "new_name": new_name,
    }

def test_asset_cross_makerspace_rebind_is_rejected():
    source_space = make_space("qr-rebind-asset-source")
    destination_space = make_space("qr-rebind-asset-dest")
    actor = make_user(
        "qr-rebind-asset-superadmin",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )
    source = make_product(source_space, name="Source Product")
    destination_product = make_product(destination_space, name="Asset Product")
    asset = InventoryAsset.objects.create(
        makerspace=destination_space,
        product=destination_product,
        asset_tag="ASSET-1",
    )
    qr = _qr(source, actor)

    response = authenticated_client(actor).post(
        f"/api/v1/admin/qr/{qr.id}/rebind-target",
        {
            "target_type": QrCode.TargetType.ASSET,
            "target_id": asset.id,
            "new_name": "ASSET-2",
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data[0] == "Only products can be rebound across makerspaces."


def test_cross_makerspace_rebind_rejects_asset_source_qr():
    source_space = make_space("qr-rebind-source-asset-source")
    destination_space = make_space("qr-rebind-source-asset-dest")
    actor = make_user(
        "qr-rebind-source-asset-superadmin",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )
    source_product = make_product(source_space, name="Source Product")
    source_asset = InventoryAsset.objects.create(
        makerspace=source_space,
        product=source_product,
        asset_tag="SOURCE-ASSET-1",
    )
    target = make_product(destination_space, name="Destination Product")
    qr = QrCode.objects.create(
        makerspace=source_space,
        target_type=QrCode.TargetType.ASSET,
        target_id=source_asset.id,
        created_by=actor,
    )

    response = authenticated_client(actor).post(
        f"/api/v1/admin/qr/{qr.id}/rebind-target",
        _rebind_payload(target),
        format="json",
    )

    assert response.status_code == 400
    assert response.data[0] == "Only products can be rebound across makerspaces."
    qr.refresh_from_db()
    assert qr.makerspace_id == source_space.id
    assert qr.target_type == QrCode.TargetType.ASSET
    assert qr.target_id == source_asset.id
