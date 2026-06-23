import uuid
from unittest.mock import Mock

import pytest

from apps.boxes.models import Box, BoxScan, QrCode, QrScanEvent
from apps.evidence.models import EvidencePhoto
from apps.hardware_requests.models import (
    HardwareRequest,
    HardwareRequestItem,
    HardwareRequestItemAsset,
    ReturnEvent,
)
from apps.inventory.models import InventoryAsset, InventoryProduct, TrackingMode
from tests.return_helpers import (
    authenticated_client,
    make_member,
    make_space,
    return_payload,
    return_url,
)

pytestmark = pytest.mark.django_db


def make_product(makerspace, name="Serialized Scope", **overrides):
    defaults = {
        "makerspace": makerspace,
        "name": name,
        "description": f"{name} description",
        "total_quantity": 10,
        "available_quantity": 10,
        "reserved_quantity": 0,
        "issued_quantity": 0,
        "damaged_quantity": 0,
        "lost_quantity": 0,
        "is_public": True,
        "is_archived": False,
    }
    defaults.update(overrides)
    return InventoryProduct.objects.create(**defaults)


def make_asset(makerspace, product, *, status=InventoryAsset.Status.AVAILABLE):
    return InventoryAsset.objects.create(
        makerspace=makerspace,
        product=product,
        asset_tag=f"A-{uuid.uuid4().hex[:8]}",
        status=status,
    )


def make_asset_qr(makerspace, asset):
    return QrCode.objects.create(
        makerspace=makerspace,
        target_type=QrCode.TargetType.ASSET,
        target_id=asset.id,
    )


def make_box(makerspace):
    return Box.objects.create(makerspace=makerspace, label=f"B-{uuid.uuid4().hex[:8]}")


def make_issue_evidence(makerspace, actor):
    return EvidencePhoto.objects.create(
        makerspace=makerspace,
        evidence_type=EvidencePhoto.EvidenceType.ISSUE,
        object_key=f"evidence/{makerspace.id}/issue/{uuid.uuid4().hex}",
        uploaded_by=actor,
    )


def make_accepted_request(makerspace, product, quantity, actor):
    requester = make_member(
        f"requester-{makerspace.slug}-{uuid.uuid4().hex[:8]}",
        makerspace,
    )
    hardware_request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        status=HardwareRequest.Status.ACCEPTED,
    )
    HardwareRequestItem.objects.create(
        request=hardware_request,
        product=product,
        requested_quantity=quantity,
        accepted_quantity=quantity,
    )
    product.available_quantity -= quantity
    product.reserved_quantity += quantity
    product.save(update_fields=["available_quantity", "reserved_quantity", "updated_at"])
    box = make_box(makerspace)
    hardware_request.assigned_box = box
    hardware_request.save(update_fields=["assigned_box", "updated_at"])
    BoxScan.objects.create(
        makerspace=makerspace,
        box=box,
        request=hardware_request,
        actor=actor,
        context=BoxScan.Context.ISSUE,
    )
    return hardware_request


def issue_url(hardware_request):
    return f"/api/v1/admin/requests/{hardware_request.id}/issue"


def issue_payload(evidence, payloads=None):
    data = {"evidence_id": evidence.id, "remark": "Handed out."}
    if payloads is not None:
        data["asset_qr_payloads"] = payloads
    return data


def issue_request(client, hardware_request, evidence, payloads=None):
    return client.post(
        issue_url(hardware_request),
        issue_payload(evidence, payloads),
        format="json",
    )


def setup_individual_issue(slug, quantity=1):
    makerspace = make_space(slug)
    admin = make_member(f"{slug}-admin", makerspace)
    product = make_product(
        makerspace,
        tracking_mode=TrackingMode.INDIVIDUAL,
        total_quantity=quantity + 3,
        available_quantity=quantity + 3,
    )
    hardware_request = make_accepted_request(makerspace, product, quantity, admin)
    evidence = make_issue_evidence(makerspace, admin)
    return makerspace, admin, product, hardware_request, evidence


def test_individual_issue_without_scans_is_rejected(monkeypatch):
    _, admin, _, hardware_request, evidence = setup_individual_issue("serialized-no-scan")
    monkeypatch.setattr("apps.evidence.storage.object_exists", Mock(return_value=True))

    response = issue_request(authenticated_client(admin), hardware_request, evidence)

    assert response.status_code == 400
    assert response.data["detail"] == (
        "Individual-tracked products require scanned asset QR codes for handout."
    )


def test_individual_issue_with_correct_scans_issues_assets_and_links(monkeypatch):
    makerspace, admin, product, hardware_request, evidence = setup_individual_issue(
        "serialized-correct",
        quantity=2,
    )
    assets = [make_asset(makerspace, product), make_asset(makerspace, product)]
    qrs = [make_asset_qr(makerspace, asset) for asset in assets]
    monkeypatch.setattr("apps.evidence.storage.object_exists", Mock(return_value=True))

    response = issue_request(
        authenticated_client(admin),
        hardware_request,
        evidence,
        [qr.payload for qr in qrs],
    )

    assert response.status_code == 200
    assert list(
        InventoryAsset.objects.filter(pk__in=[asset.pk for asset in assets])
        .order_by("pk")
        .values_list("status", flat=True)
    ) == [InventoryAsset.Status.ISSUED, InventoryAsset.Status.ISSUED]
    item = hardware_request.items.get()
    assert set(item.asset_links.values_list("asset_id", "outcome")) == {
        (assets[0].id, HardwareRequestItemAsset.Outcome.ISSUED),
        (assets[1].id, HardwareRequestItemAsset.Outcome.ISSUED),
    }
    assert QrScanEvent.objects.filter(
        request=hardware_request,
        context=QrScanEvent.Context.ISSUE,
    ).count() == 2


@pytest.mark.parametrize(
    "slug,asset_factory",
    [
        ("serialized-wrong-product", "wrong_product"),
        ("serialized-issued-asset", "issued"),
        ("serialized-cross-space", "cross_space"),
    ],
)
def test_individual_issue_rejects_invalid_asset_scans(monkeypatch, slug, asset_factory):
    makerspace, admin, product, hardware_request, evidence = setup_individual_issue(slug)
    if asset_factory == "wrong_product":
        other_product = make_product(
            makerspace,
            name="Other serialized item",
            tracking_mode=TrackingMode.INDIVIDUAL,
        )
        asset = make_asset(makerspace, other_product)
        qr_space = makerspace
    elif asset_factory == "issued":
        asset = make_asset(makerspace, product, status=InventoryAsset.Status.ISSUED)
        qr_space = makerspace
    else:
        other_space = make_space(f"{slug}-other")
        other_product = make_product(
            other_space,
            tracking_mode=TrackingMode.INDIVIDUAL,
        )
        asset = make_asset(other_space, other_product)
        qr_space = other_space
    qr = make_asset_qr(qr_space, asset)
    monkeypatch.setattr("apps.evidence.storage.object_exists", Mock(return_value=True))

    response = issue_request(
        authenticated_client(admin),
        hardware_request,
        evidence,
        [qr.payload],
    )

    assert response.status_code == 400
    hardware_request.refresh_from_db()
    product.refresh_from_db()
    assert hardware_request.status == HardwareRequest.Status.ACCEPTED
    assert (product.reserved_quantity, product.issued_quantity) == (1, 0)
    assert HardwareRequestItemAsset.objects.count() == 0


def test_individual_issue_rejects_second_issue_of_same_asset(monkeypatch):
    makerspace, admin, product, first_request, first_evidence = setup_individual_issue(
        "serialized-reissue-first"
    )
    second_request = make_accepted_request(makerspace, product, 1, admin)
    second_evidence = make_issue_evidence(makerspace, admin)
    asset = make_asset(makerspace, product)
    qr = make_asset_qr(makerspace, asset)
    monkeypatch.setattr("apps.evidence.storage.object_exists", Mock(return_value=True))
    client = authenticated_client(admin)

    first = issue_request(client, first_request, first_evidence, [qr.payload])
    second = issue_request(client, second_request, second_evidence, [qr.payload])

    assert first.status_code == 200
    assert second.status_code == 400
    assert HardwareRequestItemAsset.objects.count() == 1
    asset.refresh_from_db()
    assert asset.status == InventoryAsset.Status.ISSUED


@pytest.mark.parametrize("payload_count", [1, 3])
def test_individual_issue_rejects_too_few_or_too_many_scans(monkeypatch, payload_count):
    makerspace, admin, product, hardware_request, evidence = setup_individual_issue(
        f"serialized-count-{payload_count}",
        quantity=2,
    )
    qrs = [
        make_asset_qr(makerspace, make_asset(makerspace, product))
        for _ in range(payload_count)
    ]
    monkeypatch.setattr("apps.evidence.storage.object_exists", Mock(return_value=True))

    response = issue_request(
        authenticated_client(admin),
        hardware_request,
        evidence,
        [qr.payload for qr in qrs],
    )

    assert response.status_code == 400
    assert HardwareRequestItemAsset.objects.count() == 0
