import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.boxes.models import Box, QrCode, QrScanEvent
from apps.evidence.models import EvidencePhoto
from apps.hardware_requests.models import HardwareRequest, PublicToolLoan
from apps.inventory.models import InventoryAsset, InventoryProduct, TrackingMode
from apps.makerspaces.models import Makerspace
from apps.hardware_requests.workflow_utils import get_or_create_requester

pytestmark = pytest.mark.django_db

_current_makerspace = None


def make_space(slug="self-checkout-space"):
    return Makerspace.objects.create(name=slug, slug=slug)


def make_product(makerspace, **overrides):
    defaults = {
        "makerspace": makerspace,
        "name": "USB Logic Analyzer",
        "total_quantity": 2,
        "available_quantity": 2,
        "is_public": True,
        "is_archived": False,
    }
    defaults.update(overrides)
    return InventoryProduct.objects.create(**defaults)


def make_qr(makerspace, product):
    return QrCode.objects.create(
        makerspace=makerspace,
        target_type=QrCode.TargetType.PRODUCT,
        target_id=product.id,
    )


def make_asset_qr(makerspace, asset):
    return QrCode.objects.create(
        makerspace=makerspace,
        target_type=QrCode.TargetType.ASSET,
        target_id=asset.id,
    )


def checkout_url(makerspace):
    global _current_makerspace
    _current_makerspace = makerspace
    return f"/api/v1/public/{makerspace.slug}/tools/checkout"


def return_url(makerspace):
    global _current_makerspace
    _current_makerspace = makerspace
    return f"/api/v1/public/{makerspace.slug}/tools/return"


def api_client():
    return APIClient(REMOTE_ADDR="10.20.30.40")


def checkout_payload(payload, **overrides):
    body = {
        "payload": payload,
        "requester_name": "Self Checkout",
        "contact_email": "member-1@example.com",
        "contact_phone": "+15550101010",
    }
    body.update(overrides)
    if "evidence_id" not in body and _current_makerspace_is_live():
        body["evidence_id"] = _public_evidence(
            body["contact_email"],
            EvidencePhoto.EvidenceType.ISSUE,
        ).id
    return body


def return_payload(payload, identifier="member-1@example.com", remark="Returned in good condition.", **overrides):
    body = {
        "identifier": identifier,
        "payload": payload,
        "remark": remark,
        "evidence_id": _public_evidence(identifier, EvidencePhoto.EvidenceType.RETURN).id,
    }
    body.update(overrides)
    return body

def _current_makerspace_is_live():
    return _current_makerspace is not None and Makerspace.objects.filter(pk=_current_makerspace.pk).exists()

def _public_evidence(identifier, evidence_type):
    assert _current_makerspace is not None
    requester = get_or_create_requester(identifier)
    return EvidencePhoto.objects.create(
        makerspace=_current_makerspace,
        evidence_type=evidence_type,
        object_key=f"evidence/{_current_makerspace.id}/{evidence_type}/{identifier}-{EvidencePhoto.objects.count() + 1}",
        uploaded_by=requester,
    )

@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_public_checkout_requires_tool_opt_in():
    makerspace = make_space("checkout-disabled")
    product = make_product(makerspace, public_self_checkout_enabled=False)
    qr = make_qr(makerspace, product)

    response = api_client().post(
        checkout_url(makerspace),
        checkout_payload(qr.payload),
        format="json",
    )

    assert response.status_code == 400
    assert HardwareRequest.objects.count() == 0
    product.refresh_from_db()
    assert product.available_quantity == 2
    assert product.issued_quantity == 0


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_public_checkout_requires_public_self_checkout_flags():
    makerspace = make_space("checkout-private")
    product = make_product(
        makerspace,
        is_public=False,
        public_self_checkout_enabled=False,
    )
    qr = make_qr(makerspace, product)

    response = api_client().post(
        checkout_url(makerspace),
        checkout_payload(qr.payload),
        format="json",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "Tool is not enabled for public self-checkout."
    assert HardwareRequest.objects.count() == 0
    product.refresh_from_db()
    assert product.available_quantity == 2
    assert product.issued_quantity == 0


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
@pytest.mark.parametrize("missing_field", ["requester_name", "contact_email", "contact_phone"])
def test_public_checkout_requires_name_email_and_phone(missing_field):
    makerspace = make_space(f"checkout-missing-{missing_field.replace('_', '-')}")
    product = make_product(makerspace, public_self_checkout_enabled=True)
    qr = make_qr(makerspace, product)
    payload = checkout_payload(qr.payload)
    payload.pop(missing_field)

    response = api_client().post(
        checkout_url(makerspace),
        payload,
        format="json",
    )

    assert response.status_code == 400
    assert missing_field in response.data
    assert HardwareRequest.objects.count() == 0


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_public_checkout_rejects_product_qr_for_individual_tracked_product():
    makerspace = make_space("checkout-individual-product-qr")
    product = make_product(
        makerspace,
        public_self_checkout_enabled=True,
        tracking_mode=TrackingMode.INDIVIDUAL,
    )
    qr = make_qr(makerspace, product)

    response = api_client().post(
        checkout_url(makerspace),
        checkout_payload(qr.payload),
        format="json",
    )

    assert response.status_code == 400
    assert response.data["detail"] == (
        "Individual-tracked products require a scanned asset QR."
    )
    assert HardwareRequest.objects.count() == 0
    product.refresh_from_db()
    assert product.available_quantity == 2
    assert product.issued_quantity == 0


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_public_checkout_accepts_asset_qr_for_individual_tracked_product():
    makerspace = make_space("checkout-individual-asset-qr")
    product = make_product(
        makerspace,
        public_self_checkout_enabled=True,
        tracking_mode=TrackingMode.INDIVIDUAL,
        total_quantity=1,
        available_quantity=1,
    )
    asset = InventoryAsset.objects.create(
        makerspace=makerspace,
        product=product,
        asset_tag="IND-PUBLIC-1",
        public_self_checkout_enabled=True,
    )
    qr = make_asset_qr(makerspace, asset)

    response = api_client().post(
        checkout_url(makerspace),
        checkout_payload(qr.payload),
        format="json",
    )

    assert response.status_code == 201
    assert response.data["items"] == [{"product_name": product.name, "quantity": 1}]
    asset.refresh_from_db()
    assert asset.status == InventoryAsset.Status.ISSUED
    product.refresh_from_db()
    assert product.available_quantity == 0
    assert product.issued_quantity == 1


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_public_checkout_rejects_box_qr_fallback_for_individual_tracked_product():
    makerspace = make_space("checkout-individual-box")
    box = Box.objects.create(makerspace=makerspace, label="Individual shelf")
    product = make_product(
        makerspace,
        box=box,
        public_self_checkout_enabled=True,
        tracking_mode=TrackingMode.INDIVIDUAL,
        total_quantity=1,
        available_quantity=1,
    )
    qr = QrCode.objects.create(
        makerspace=makerspace,
        target_type=QrCode.TargetType.BOX,
        target_id=box.id,
    )

    response = api_client().post(
        checkout_url(makerspace),
        checkout_payload(qr.payload),
        format="json",
    )

    assert response.status_code == 400
    assert response.data["detail"] == (
        "Individual-tracked products require a scanned asset QR."
    )
    assert HardwareRequest.objects.count() == 0
    product.refresh_from_db()
    assert product.available_quantity == 1
    assert product.issued_quantity == 0


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_public_checkout_and_return_move_inventory_and_record_scans():
    makerspace = make_space("checkout-return")
    product = make_product(makerspace, public_self_checkout_enabled=True)
    qr = make_qr(makerspace, product)
    client = api_client()

    checkout = client.post(
        checkout_url(makerspace),
        checkout_payload(qr.payload),
        format="json",
    )

    assert checkout.status_code == 201
    assert checkout.data["status"] == PublicToolLoan.Status.CHECKED_OUT
    assert checkout.data["items"] == [
        {"product_name": "USB Logic Analyzer", "quantity": 1}
    ]
    product.refresh_from_db()
    assert product.available_quantity == 1
    assert product.issued_quantity == 1
    request = HardwareRequest.objects.get()
    assert request.status == HardwareRequest.Status.ISSUED
    assert request.requester_name == "Self Checkout"
    assert request.requester_contact_email == "member-1@example.com"
    assert request.requester_contact_phone == "+15550101010"
    loan = PublicToolLoan.objects.get()
    assert request.return_due_at == loan.due_at
    assert QrScanEvent.objects.get(context=QrScanEvent.Context.ISSUE).request == request

    returned = client.post(
        return_url(makerspace),
        return_payload(qr.payload),
        format="json",
    )

    assert returned.status_code == 200
    assert returned.data["status"] == PublicToolLoan.Status.RETURNED
    product.refresh_from_db()
    assert product.available_quantity == 2
    assert product.issued_quantity == 0
    request.refresh_from_db()
    assert request.status == HardwareRequest.Status.RETURNED
    assert QrScanEvent.objects.filter(context=QrScanEvent.Context.RETURN).count() == 1


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_public_box_checkout_return_restores_all_items():
    makerspace = make_space("checkout-return-box")
    box = Box.objects.create(makerspace=makerspace, label="Loan shelf")
    product_a = make_product(
        makerspace,
        name="Logic Analyzer",
        box=box,
        public_self_checkout_enabled=True,
    )
    product_b = make_product(
        makerspace,
        name="Oscilloscope Probe",
        box=box,
        public_self_checkout_enabled=True,
    )
    qr = QrCode.objects.create(
        makerspace=makerspace,
        target_type=QrCode.TargetType.BOX,
        target_id=box.id,
    )
    client = api_client()

    checkout = client.post(
        checkout_url(makerspace),
        checkout_payload(qr.payload),
        format="json",
    )

    assert checkout.status_code == 201
    assert sorted(item["product_name"] for item in checkout.data["items"]) == [
        "Logic Analyzer",
        "Oscilloscope Probe",
    ]
    product_a.refresh_from_db()
    product_b.refresh_from_db()
    assert product_a.available_quantity == 1
    assert product_a.issued_quantity == 1
    assert product_b.available_quantity == 1
    assert product_b.issued_quantity == 1

    returned = client.post(
        return_url(makerspace),
        return_payload(qr.payload),
        format="json",
    )

    assert returned.status_code == 200
    product_a.refresh_from_db()
    product_b.refresh_from_db()
    assert product_a.available_quantity == 2
    assert product_a.issued_quantity == 0
    assert product_b.available_quantity == 2
    assert product_b.issued_quantity == 0


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_public_return_requires_same_verified_user():
    makerspace = make_space("checkout-other-user")
    product = make_product(makerspace, public_self_checkout_enabled=True)
    qr = make_qr(makerspace, product)
    client = api_client()
    client.post(
        checkout_url(makerspace),
        checkout_payload(qr.payload),
        format="json",
    )

    response = client.post(
        return_url(makerspace),
        return_payload(qr.payload, identifier="member-2@example.com"),
        format="json",
    )

    assert response.status_code == 403
    assert response.data["code"] == "requester_blocked"
    assert PublicToolLoan.objects.get().status == PublicToolLoan.Status.CHECKED_OUT



