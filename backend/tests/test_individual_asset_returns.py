import uuid
from unittest.mock import Mock

import pytest

from apps.boxes.models import QrScanEvent
from apps.evidence.models import EvidencePhoto
from apps.hardware_requests.models import HardwareRequestItemAsset, ReturnEvent
from apps.inventory.models import InventoryAsset
from tests.return_helpers import authenticated_client, return_payload, return_url
from tests.test_serialized_handout import (
    issue_request,
    make_asset,
    make_asset_qr,
    make_issue_evidence,
    make_product,
    setup_individual_issue,
)

pytestmark = pytest.mark.django_db


def make_return_evidence(makerspace, actor):
    return EvidencePhoto.objects.create(
        makerspace=makerspace,
        evidence_type=EvidencePhoto.EvidenceType.RETURN,
        object_key=f"evidence/{makerspace.id}/return/{uuid.uuid4().hex}",
        uploaded_by=actor,
    )


def test_quantity_mode_issue_and_return_do_not_require_asset_payloads(monkeypatch):
    from tests.test_serialized_handout import make_accepted_request

    makerspace, admin, product = _quantity_setup()
    hardware_request = make_accepted_request(makerspace, product, 2, admin)
    issue_evidence = make_issue_evidence(makerspace, admin)
    return_evidence = make_return_evidence(makerspace, admin)
    monkeypatch.setattr("apps.evidence.storage.object_exists", Mock(return_value=True))
    client = authenticated_client(admin)

    issued = issue_request(client, hardware_request, issue_evidence)
    returned = client.post(
        return_url(hardware_request),
        return_payload(hardware_request, return_evidence),
        format="json",
    )

    assert issued.status_code == 200
    assert returned.status_code == 200
    product.refresh_from_db()
    assert (product.available_quantity, product.issued_quantity) == (5, 0)
    assert HardwareRequestItemAsset.objects.count() == 0


def test_return_payload_exposes_issued_individual_assets(monkeypatch):
    makerspace, admin, _, hardware_request, issue_evidence = setup_individual_issue(
        "serialized-return-payload",
        quantity=2,
    )
    assets = _issue_assets(monkeypatch, admin, hardware_request, issue_evidence, quantity=2)

    data = authenticated_client(admin).get(
        f"/api/v1/admin/makerspace/{makerspace.id}/active-loans"
    ).data

    issued_assets = data["results"][0]["items"][0]["issued_assets"]
    assert [asset["asset_id"] for asset in issued_assets] == [asset.id for asset in assets]
    assert [asset["asset_tag"] for asset in issued_assets] == [asset.asset_tag for asset in assets]


def test_exact_individual_return_flips_selected_asset_only(monkeypatch):
    makerspace, admin, _, hardware_request, issue_evidence = setup_individual_issue(
        "serialized-return-exact",
        quantity=3,
    )
    assets = _issue_assets(monkeypatch, admin, hardware_request, issue_evidence, quantity=3)
    evidence = make_return_evidence(makerspace, admin)
    item = hardware_request.items.get()
    payload = return_payload(hardware_request, evidence, remark="One damaged.")
    payload["resolutions"] = [
        {
            "item_id": item.id,
            "returned": 0,
            "damaged": 1,
            "missing": 0,
            "assets": [{"asset_id": assets[1].id, "outcome": "damaged"}],
        }
    ]

    response = authenticated_client(admin).post(return_url(hardware_request), payload, format="json")

    assert response.status_code == 200
    assert InventoryAsset.objects.get(pk=assets[0].pk).status == InventoryAsset.Status.ISSUED
    assert InventoryAsset.objects.get(pk=assets[1].pk).status == InventoryAsset.Status.DAMAGED
    assert InventoryAsset.objects.get(pk=assets[2].pk).status == InventoryAsset.Status.ISSUED
    assert item.asset_links.get(asset=assets[1]).outcome == HardwareRequestItemAsset.Outcome.DAMAGED
    assert QrScanEvent.objects.filter(context=QrScanEvent.Context.RETURN, request=hardware_request).count() == 1
    hardware_request.refresh_from_db()
    assert hardware_request.status == "partially_returned"


def test_legacy_individual_return_all_remaining_as_returned_still_works(monkeypatch):
    makerspace, admin, _, hardware_request, issue_evidence = setup_individual_issue(
        "serialized-return-legacy-all",
        quantity=2,
    )
    assets = _issue_assets(monkeypatch, admin, hardware_request, issue_evidence, quantity=2)
    evidence = make_return_evidence(makerspace, admin)
    item = hardware_request.items.get()
    payload = return_payload(hardware_request, evidence, remark="All returned.")
    payload["resolutions"] = [{"item_id": item.id, "returned": 2, "damaged": 0, "missing": 0}]

    response = authenticated_client(admin).post(return_url(hardware_request), payload, format="json")

    assert response.status_code == 200
    assert set(
        InventoryAsset.objects.filter(pk__in=[asset.pk for asset in assets]).values_list("status", flat=True)
    ) == {InventoryAsset.Status.AVAILABLE}
    assert item.asset_links.filter(outcome=HardwareRequestItemAsset.Outcome.ISSUED).count() == 0
    assert ReturnEvent.objects.filter(request=hardware_request).count() == 1


@pytest.mark.parametrize(
    "resolution",
    [
        {"returned": 1, "damaged": 0, "missing": 0},
        {"returned": 0, "damaged": 1, "missing": 0},
        {"returned": 0, "damaged": 0, "missing": 1},
    ],
)
def test_individual_return_without_asset_identity_rejects_partial_or_issue(monkeypatch, resolution):
    makerspace, admin, _, hardware_request, issue_evidence = setup_individual_issue(
        f"serialized-return-reject-{resolution['returned']}{resolution['damaged']}{resolution['missing']}",
        quantity=2,
    )
    assets = _issue_assets(monkeypatch, admin, hardware_request, issue_evidence, quantity=2)
    evidence = make_return_evidence(makerspace, admin)
    item = hardware_request.items.get()
    payload = return_payload(hardware_request, evidence, remark="Rejected.")
    payload["resolutions"] = [{"item_id": item.id, **resolution}]

    response = authenticated_client(admin).post(return_url(hardware_request), payload, format="json")

    assert response.status_code == 400
    assert response.data["detail"] == "Individual-tracked returns require exact asset identity."
    assert set(
        InventoryAsset.objects.filter(pk__in=[asset.pk for asset in assets]).values_list("status", flat=True)
    ) == {InventoryAsset.Status.ISSUED}


def _quantity_setup():
    from tests.return_helpers import make_member, make_space

    makerspace = make_space("serialized-quantity-return")
    admin = make_member("serialized-quantity-return-admin", makerspace)
    product = make_product(makerspace, total_quantity=5, available_quantity=5)
    return makerspace, admin, product


def _issue_assets(monkeypatch, admin, hardware_request, issue_evidence, *, quantity):
    item = hardware_request.items.select_related("product").get()
    assets = [make_asset(hardware_request.makerspace, item.product) for _ in range(quantity)]
    qrs = [make_asset_qr(hardware_request.makerspace, asset) for asset in assets]
    monkeypatch.setattr("apps.evidence.storage.object_exists", Mock(return_value=True))
    response = issue_request(
        authenticated_client(admin),
        hardware_request,
        issue_evidence,
        [qr.payload for qr in qrs],
    )
    assert response.status_code == 200
    return assets
