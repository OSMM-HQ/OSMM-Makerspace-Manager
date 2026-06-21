import pytest
from django.db import IntegrityError
from django.test import override_settings
from rest_framework.test import APIClient

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
from apps.makerspaces.models import MakerspaceMembership
from apps.operations.models import InventoryAdjustment
from tests.return_helpers import authenticated_client, make_member, make_product, make_space, make_user

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


@pytest.mark.parametrize(
    ("membership_role", "global_role"),
    [
        (MakerspaceMembership.Role.SPACE_MANAGER, User.Role.SPACE_MANAGER),
        (MakerspaceMembership.Role.INVENTORY_MANAGER, User.Role.REQUESTER),
    ],
)
def test_same_makerspace_rebind_and_rename_by_qr_inventory_manager_succeeds(
    membership_role,
    global_role,
):
    makerspace = make_space(f"qr-rebind-same-{membership_role}")
    actor = make_member(
        f"qr-rebind-same-{membership_role}",
        makerspace,
        membership_role=membership_role,
        role=global_role,
    )
    source = make_product(makerspace, name="Old Drill")
    target = make_product(makerspace, name="New Drill")
    qr = _qr(source, actor)

    response = authenticated_client(actor).post(
        f"/api/v1/admin/qr/{qr.id}/rebind-target",
        _rebind_payload(target, "Renamed Drill"),
        format="json",
    )

    assert response.status_code == 200
    qr.refresh_from_db()
    target.refresh_from_db()
    assert qr.makerspace_id == makerspace.id
    assert qr.target_id == target.id
    assert target.name == "Renamed Drill"
    assert response.data["target"]["name"] == "Renamed Drill"
    assert QrScanEvent.objects.get(qr_code=qr).context == QrScanEvent.Context.REASSIGNMENT


def test_rebind_rejects_overlong_new_name():
    makerspace = make_space("qr-rebind-longname")
    actor = make_member(
        "qr-rebind-longname-mgr",
        makerspace,
        membership_role=MakerspaceMembership.Role.SPACE_MANAGER,
        role=User.Role.SPACE_MANAGER,
    )
    source = make_product(makerspace, name="Old")
    target = make_product(makerspace, name="New")
    qr = _qr(source, actor)

    response = authenticated_client(actor).post(
        f"/api/v1/admin/qr/{qr.id}/rebind-target",
        _rebind_payload(target, "x" * 101),
        format="json",
    )

    assert response.status_code == 400
    qr.refresh_from_db()
    assert qr.target_id == source.id  # unchanged


def test_cross_makerspace_rebind_by_superadmin_moves_qr_and_renames_target():
    source_space = make_space("qr-rebind-cross-source")
    destination_space = make_space("qr-rebind-cross-dest")
    actor = make_user(
        "qr-rebind-superadmin",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )
    source = make_product(source_space, name="Source Product")
    target = make_product(destination_space, name="Destination Product")
    qr = _qr(source, actor)

    response = authenticated_client(actor).post(
        f"/api/v1/admin/qr/{qr.id}/rebind-target",
        _rebind_payload(target, "Moved Product"),
        format="json",
    )

    assert response.status_code == 200
    qr.refresh_from_db()
    target.refresh_from_db()
    assert qr.makerspace_id == destination_space.id
    assert qr.target_id == target.id
    assert target.name == "Moved Product"
    assert response.data["qr"]["makerspace"] == destination_space.id
    assert QrScanEvent.objects.get(qr_code=qr).makerspace_id == destination_space.id


def test_cross_makerspace_rebind_by_non_superadmin_manager_is_denied():
    source_space = make_space("qr-rebind-cross-deny-source")
    destination_space = make_space("qr-rebind-cross-deny-dest")
    actor = make_member("qr-rebind-cross-deny", source_space)
    MakerspaceMembership.objects.create(
        user=actor,
        makerspace=destination_space,
        role=MakerspaceMembership.Role.SPACE_MANAGER,
    )
    source = make_product(source_space, name="Source Product")
    target = make_product(destination_space, name="Destination Product")
    qr = _qr(source, actor)

    response = authenticated_client(actor).post(
        f"/api/v1/admin/qr/{qr.id}/rebind-target",
        _rebind_payload(target),
        format="json",
    )

    assert response.status_code == 403
    qr.refresh_from_db()
    assert qr.makerspace_id == source_space.id
    assert qr.target_id == source.id


def test_cross_makerspace_rebind_denies_hidden_source_or_destination():
    source_space = make_space("qr-rebind-hidden-source")
    destination_space = make_space("qr-rebind-hidden-dest")
    make_member("qr-rebind-hidden-source-manager", source_space)
    make_member("qr-rebind-hidden-dest-manager", destination_space)
    source_space.superadmin_access_enabled = False
    source_space.save(update_fields=["superadmin_access_enabled"])
    actor = make_user(
        "qr-rebind-hidden-superadmin",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )
    source = make_product(source_space, name="Hidden Source Product")
    target = make_product(destination_space, name="Hidden Destination Product")
    qr = _qr(source, actor)

    hidden_source = authenticated_client(actor).post(
        f"/api/v1/admin/qr/{qr.id}/rebind-target",
        _rebind_payload(target),
        format="json",
    )
    source_space.superadmin_access_enabled = True
    source_space.save(update_fields=["superadmin_access_enabled"])
    destination_space.superadmin_access_enabled = False
    destination_space.save(update_fields=["superadmin_access_enabled"])
    hidden_destination = authenticated_client(actor).post(
        f"/api/v1/admin/qr/{qr.id}/rebind-target",
        _rebind_payload(target),
        format="json",
    )

    assert hidden_source.status_code == 403
    assert hidden_destination.status_code == 403
    qr.refresh_from_db()
    assert qr.makerspace_id == source_space.id
    assert qr.target_id == source.id


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_rebind_blocked_when_qr_has_outstanding_loan():
    makerspace = make_space("qr-rebind-loan")
    actor = make_member("qr-rebind-loan-manager", makerspace)
    source = make_product(makerspace, public_self_checkout_enabled=True)
    target = make_product(makerspace, name="Loan Target")
    qr = _qr(source, actor)
    checkout = APIClient().post(
        f"/api/v1/public/{makerspace.slug}/tools/checkout",
        {"identifier": "member-1", "payload": qr.payload},
        format="json",
    )
    assert checkout.status_code == 201

    response = authenticated_client(actor).post(
        f"/api/v1/admin/qr/{qr.id}/rebind-target",
        _rebind_payload(target),
        format="json",
    )

    assert response.status_code == 409
    assert response.data["detail"] == "Cannot rebind a QR with an outstanding loan."


def test_rebind_destination_conflict_returns_409():
    makerspace = make_space("qr-rebind-conflict")
    actor = make_member("qr-rebind-conflict-manager", makerspace)
    source = make_product(makerspace, name="Source Product")
    target = make_product(makerspace, name="Taken Product")
    qr = _qr(source, actor)
    _qr(target, actor)

    response = authenticated_client(actor).post(
        f"/api/v1/admin/qr/{qr.id}/rebind-target",
        _rebind_payload(target),
        format="json",
    )

    assert response.status_code == 409
    assert response.data["detail"] == "Target already has an active QR code."
    qr.refresh_from_db()
    assert qr.target_id == source.id


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
