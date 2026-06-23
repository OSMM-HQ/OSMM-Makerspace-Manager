import pytest

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.boxes.models import QrCode, QrScanEvent
from apps.hardware_requests.models import (
    HardwareRequest,
    HardwareRequestItem,
    HardwareRequestItemAsset,
    PublicToolLoan,
)
from apps.inventory.models import InventoryAsset, TrackingMode
from apps.operations.models import InventoryAdjustment
from tests.return_helpers import authenticated_client, make_product, make_space, make_user

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

def test_cross_makerspace_asset_move_happy_path_creates_dest_product_and_audit():
    source, dest, actor, source_product, asset, qr = _move_setup("asset-move-happy")

    response = _move_response(
        actor,
        qr,
        _move_payload(asset, dest, new_name="Moved Asset"),
    )

    assert response.status_code == 200
    asset.refresh_from_db()
    qr.refresh_from_db()
    source_product.refresh_from_db()
    dest_product = asset.product
    assert asset.makerspace_id == dest.id
    assert asset.asset_tag == "Moved Asset"
    assert asset.box_id is None
    assert asset.public_self_checkout_enabled is False
    assert dest_product.makerspace_id == dest.id
    assert dest_product.tracking_mode == TrackingMode.INDIVIDUAL
    assert dest_product.is_public is False
    assert qr.makerspace_id == dest.id
    assert qr.target_id == asset.id
    assert (source_product.available_quantity, source_product.total_quantity) == (0, 0)
    assert (dest_product.available_quantity, dest_product.total_quantity) == (1, 1)
    assert InventoryAdjustment.objects.filter(
        product__in=[source_product, dest_product],
        reason__startswith="Cross-makerspace asset move",
    ).count() == 2
    assert QrScanEvent.objects.get(
        qr_code=qr,
        context=QrScanEvent.Context.REASSIGNMENT,
    ).makerspace_id == dest.id
    audit = AuditLog.objects.get(action="inventory.asset_moved_makerspace")
    assert audit.makerspace_id == dest.id
    assert audit.meta == {
        "old_makerspace_id": source.id,
        "new_makerspace_id": dest.id,
        "asset_id": asset.id,
        "dest_product_id": dest_product.id,
        "old_tag": "asset-move-happy-A1",
        "new_tag": "Moved Asset",
    }


def test_cross_makerspace_asset_move_target_id_mismatch_returns_400():
    _, dest, actor, _, asset, qr = _move_setup("asset-move-mismatch")

    response = _move_response(
        actor,
        qr,
        _move_payload(asset, dest, target_id=asset.id + 1000),
    )

    assert response.status_code == 400
    asset.refresh_from_db()
    assert asset.makerspace_id == qr.makerspace_id


def test_cross_makerspace_asset_move_requires_available_asset():
    source, dest, actor, _, asset, qr = _move_setup("asset-move-issued")
    asset.status = InventoryAsset.Status.ISSUED
    asset.save(update_fields=["status", "updated_at"])

    response = _move_response(actor, qr, _move_payload(asset, dest))

    assert response.status_code == 409
    asset.refresh_from_db()
    assert asset.makerspace_id == source.id


def test_cross_makerspace_asset_move_rejects_qr_active_loan():
    source, dest, actor, _, asset, qr = _move_setup("asset-move-qr-loan")
    requester = make_user("asset-move-qr-loan-requester", access_status=User.AccessStatus.ACTIVE)
    hardware_request = HardwareRequest.objects.create(
        makerspace=source,
        requester=requester,
        requester_username=requester.username,
        status=HardwareRequest.Status.ISSUED,
    )
    PublicToolLoan.objects.create(
        makerspace=source,
        qr_code=qr,
        qr_ids=[qr.id],
        request=hardware_request,
        requester=requester,
        target_type=QrCode.TargetType.ASSET,
        target_id=asset.id,
        target_label=asset.asset_tag,
        asset_ids=[],
    )

    response = _move_response(actor, qr, _move_payload(asset, dest))

    assert response.status_code == 409
    asset.refresh_from_db()
    assert asset.makerspace_id == source.id


def test_cross_makerspace_asset_move_rejects_outstanding_request_asset_link():
    source, dest, actor, product, asset, qr = _move_setup("asset-move-link")
    requester = make_user("asset-move-link-requester", access_status=User.AccessStatus.ACTIVE)
    hardware_request = HardwareRequest.objects.create(
        makerspace=source,
        requester=requester,
        requester_username=requester.username,
        status=HardwareRequest.Status.PARTIALLY_RETURNED,
    )
    item = HardwareRequestItem.objects.create(
        request=hardware_request,
        product=product,
        requested_quantity=1,
        accepted_quantity=1,
        issued_quantity=1,
    )
    HardwareRequestItemAsset.objects.create(
        request_item=item,
        asset=asset,
        outcome=HardwareRequestItemAsset.Outcome.ISSUED,
    )

    response = _move_response(actor, qr, _move_payload(asset, dest))

    assert response.status_code == 409
    asset.refresh_from_db()
    assert asset.makerspace_id == source.id


def test_cross_makerspace_asset_move_rejects_public_tool_loan_asset_ids():
    source, dest, actor, _, asset, qr = _move_setup("asset-move-assetids")
    requester = make_user("asset-move-assetids-requester", access_status=User.AccessStatus.ACTIVE)
    hardware_request = HardwareRequest.objects.create(
        makerspace=source,
        requester=requester,
        requester_username=requester.username,
        status=HardwareRequest.Status.ISSUED,
    )
    PublicToolLoan.objects.create(
        makerspace=source,
        qr_code=None,
        qr_ids=[],
        request=hardware_request,
        requester=requester,
        target_type="direct",
        target_id=hardware_request.id,
        target_label=asset.asset_tag,
        asset_ids=[asset.id],
    )

    response = _move_response(actor, qr, _move_payload(asset, dest))

    assert response.status_code == 409
    asset.refresh_from_db()
    assert asset.makerspace_id == source.id
