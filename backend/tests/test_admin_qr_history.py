import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.boxes.models import QrCode, QrScanEvent
from apps.inventory.models import InventoryAsset, TrackingMode
from tests.return_helpers import authenticated_client, make_member, make_product, make_space

pytestmark = pytest.mark.django_db


def _qr(makerspace, target_type, target_id, payload):
    return QrCode.objects.create(
        makerspace=makerspace,
        target_type=target_type,
        target_id=target_id,
        payload=payload,
    )


def test_product_qr_history_is_scoped_and_redacted():
    makerspace = make_space("product-qr-history")
    other_space = make_space("product-qr-history-other")
    staff = make_member("product-qr-history-staff", makerspace)
    product = make_product(makerspace, name="QR Product")
    other_product = make_product(makerspace, name="Other QR Product")
    foreign_product = make_product(other_space, name="Foreign QR Product")
    qr = _qr(makerspace, QrCode.TargetType.PRODUCT, product.id, "product-secret")
    _qr(makerspace, QrCode.TargetType.PRODUCT, other_product.id, "other-secret")
    foreign_qr = _qr(other_space, QrCode.TargetType.PRODUCT, foreign_product.id, "foreign-secret")
    QrScanEvent.objects.create(
        makerspace=makerspace,
        qr_code=qr,
        actor=staff,
        context=QrScanEvent.Context.INVENTORY_CHECK,
    )
    QrScanEvent.objects.create(
        makerspace=other_space,
        qr_code=foreign_qr,
        actor=make_member("product-qr-history-foreign-staff", other_space),
        context=QrScanEvent.Context.SCANNER_LOOKUP,
    )

    response = authenticated_client(staff).get(
        reverse("admin-inventory-qr-history", kwargs={"pk": product.id})
    )

    assert response.status_code == 200
    assert response.data["product"] == product.id
    assert len(response.data["scans"]) == 1
    assert response.data["scans"][0]["context"] == QrScanEvent.Context.INVENTORY_CHECK
    assert response.data["scans"][0]["source"] == "qr_scan"
    assert "payload" not in response.data["scans"][0]
    assert "product-secret" not in str(response.data)


def test_asset_qr_history_is_scoped_and_redacted():
    makerspace = make_space("asset-qr-history")
    other_space = make_space("asset-qr-history-other")
    staff = make_member("asset-qr-history-staff", makerspace)
    product = make_product(
        makerspace,
        name="Asset QR Product",
        tracking_mode=TrackingMode.INDIVIDUAL,
    )
    asset = InventoryAsset.objects.create(
        makerspace=makerspace,
        product=product,
        asset_tag="A-1",
    )
    qr = _qr(makerspace, QrCode.TargetType.ASSET, asset.id, "asset-secret")
    QrScanEvent.objects.create(
        makerspace=makerspace,
        qr_code=qr,
        actor=staff,
        context=QrScanEvent.Context.RETURN,
    )
    outsider = make_member("asset-qr-history-outsider", other_space)

    own_response = authenticated_client(staff).get(
        reverse("admin-inventory-asset-qr-history", kwargs={"pk": asset.id})
    )
    cross_response = authenticated_client(outsider).get(
        reverse("admin-inventory-asset-qr-history", kwargs={"pk": asset.id})
    )

    assert own_response.status_code == 200
    assert own_response.data["asset"] == asset.id
    assert len(own_response.data["scans"]) == 1
    assert own_response.data["scans"][0]["context"] == QrScanEvent.Context.RETURN
    assert "payload" not in own_response.data["scans"][0]
    assert "asset-secret" not in str(own_response.data)
    assert cross_response.status_code == 404