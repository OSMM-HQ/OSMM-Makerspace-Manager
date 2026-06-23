import pytest
from django.db import IntegrityError

from apps.accounts.models import User
from apps.boxes.models import QrCode
from apps.inventory.models import InventoryAsset, TrackingMode
from apps.makerspaces.models import MakerspaceMembership
from apps.operations.models import InventoryAdjustment
from tests.return_helpers import authenticated_client, make_member, make_product, make_space, make_user

pytestmark = pytest.mark.django_db


def _asset_qr(asset, actor=None):
    return QrCode.objects.create(
        makerspace=asset.makerspace,
        target_type=QrCode.TargetType.ASSET,
        target_id=asset.id,
        created_by=actor,
    )


def _move_setup(slug="asset-move"):
    source_space = make_space(f"{slug}-source")
    destination_space = make_space(f"{slug}-dest")
    actor = make_user(
        f"{slug}-superadmin",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )
    product = make_product(
        source_space,
        name=f"{slug} Tool",
        tracking_mode=TrackingMode.INDIVIDUAL,
        total_quantity=1,
        available_quantity=1,
    )
    asset = InventoryAsset.objects.create(
        makerspace=source_space,
        product=product,
        asset_tag=f"{slug}-A1",
    )
    qr = _asset_qr(asset, actor)
    return source_space, destination_space, actor, product, asset, qr


def _move_payload(asset, destination_space, **overrides):
    payload = {
        "target_type": QrCode.TargetType.ASSET,
        "target_id": asset.id,
        "destination_makerspace_id": destination_space.id,
        "new_name": "",
    }
    payload.update(overrides)
    return payload


def _move_response(actor, qr, payload):
    return authenticated_client(actor).post(
        f"/api/v1/admin/qr/{qr.id}/rebind-target",
        payload,
        format="json",
    )

def test_cross_makerspace_asset_move_rejects_tag_collision_precheck():
    source, dest, actor, _, asset, qr = _move_setup("asset-move-tag")
    dest_product = make_product(
        dest,
        name="Existing",
        tracking_mode=TrackingMode.INDIVIDUAL,
        total_quantity=1,
        available_quantity=1,
    )
    InventoryAsset.objects.create(
        makerspace=dest,
        product=dest_product,
        asset_tag="TAKEN",
    )

    response = _move_response(actor, qr, _move_payload(asset, dest, new_name="TAKEN"))

    assert response.status_code == 409
    asset.refresh_from_db()
    assert asset.makerspace_id == source.id


def test_cross_makerspace_asset_move_integrity_error_on_asset_save_returns_409(monkeypatch):
    source, dest, actor, product, asset, qr = _move_setup("asset-move-integrity")
    original_save = InventoryAsset.save

    def fail_asset_save(self, *args, **kwargs):
        if self.pk == asset.pk and self.makerspace_id == dest.id:
            raise IntegrityError("forced asset tag race")
        return original_save(self, *args, **kwargs)

    monkeypatch.setattr(InventoryAsset, "save", fail_asset_save)

    response = _move_response(actor, qr, _move_payload(asset, dest, new_name="RACE"))

    assert response.status_code == 409
    asset.refresh_from_db()
    product.refresh_from_db()
    assert asset.makerspace_id == source.id
    assert (product.available_quantity, product.total_quantity) == (1, 1)
    assert InventoryAdjustment.objects.count() == 0


def test_cross_makerspace_asset_move_rolls_back_after_qr_save_integrity_error(monkeypatch):
    source, dest, actor, source_product, asset, qr = _move_setup("asset-move-rollback")
    original_save = QrCode.save

    def fail_qr_save(self, *args, **kwargs):
        if self.pk == qr.pk and self.makerspace_id == dest.id:
            raise IntegrityError("forced qr target race")
        return original_save(self, *args, **kwargs)

    monkeypatch.setattr(QrCode, "save", fail_qr_save)

    response = _move_response(actor, qr, _move_payload(asset, dest, new_name="Moved"))

    assert response.status_code == 409
    asset.refresh_from_db()
    qr.refresh_from_db()
    source_product.refresh_from_db()
    assert asset.makerspace_id == source.id
    assert qr.makerspace_id == source.id
    assert (source_product.available_quantity, source_product.total_quantity) == (1, 1)
    assert InventoryAdjustment.objects.count() == 0


def test_cross_makerspace_asset_move_rejects_quantity_destination_name_match():
    source, dest, actor, source_product, asset, qr = _move_setup("asset-move-quantity")
    make_product(
        dest,
        name=source_product.name,
        tracking_mode=TrackingMode.QUANTITY,
        total_quantity=2,
        available_quantity=2,
    )

    response = _move_response(actor, qr, _move_payload(asset, dest))

    assert response.status_code == 409
    asset.refresh_from_db()
    assert asset.makerspace_id == source.id


def test_cross_makerspace_asset_move_uses_explicit_destination_product():
    _, dest, actor, _, asset, qr = _move_setup("asset-move-explicit")
    explicit_product = make_product(
        dest,
        name="Explicit Destination",
        tracking_mode=TrackingMode.INDIVIDUAL,
        total_quantity=3,
        available_quantity=3,
    )

    response = _move_response(
        actor,
        qr,
        _move_payload(
            asset,
            dest,
            destination_product_id=explicit_product.id,
            new_name="Explicit Asset",
        ),
    )

    assert response.status_code == 200
    asset.refresh_from_db()
    explicit_product.refresh_from_db()
    assert asset.product_id == explicit_product.id
    assert asset.makerspace_id == dest.id
    assert explicit_product.available_quantity == 4
    assert explicit_product.total_quantity == 4


def test_cross_makerspace_asset_move_non_superadmin_is_denied():
    source, dest, _, _, asset, qr = _move_setup("asset-move-denied")
    actor = make_member("asset-move-denied-manager", source)
    MakerspaceMembership.objects.create(
        user=actor,
        makerspace=dest,
        role=MakerspaceMembership.Role.SPACE_MANAGER,
    )

    response = _move_response(actor, qr, _move_payload(asset, dest))

    assert response.status_code == 403
    asset.refresh_from_db()
    qr.refresh_from_db()
    assert asset.makerspace_id == source.id
    assert qr.makerspace_id == source.id
