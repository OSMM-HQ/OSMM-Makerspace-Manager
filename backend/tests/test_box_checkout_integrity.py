import importlib

import pytest
from django.apps import apps
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.boxes.models import Box, QrCode
from apps.evidence.models import EvidencePhoto
from apps.hardware_requests.models import HardwareRequest, PublicToolLoan
from apps.inventory.models import InventoryAsset, InventoryProduct, TrackingMode
from apps.makerspaces.models import Makerspace, MakerspaceMembership
from apps.hardware_requests.workflow_utils import get_or_create_requester

pytestmark = pytest.mark.django_db

_current_makerspace = None


def make_space(slug):
    return Makerspace.objects.create(name=slug, slug=slug)


def make_admin(makerspace):
    user = User.objects.create_user(
        username=f"admin-{makerspace.slug}",
        role=User.Role.SPACE_MANAGER,
        access_status=User.AccessStatus.ACTIVE,
    )
    MakerspaceMembership.objects.create(
        user=user,
        makerspace=makerspace,
        role=MakerspaceMembership.Role.SPACE_MANAGER,
    )
    return user


def make_product(makerspace, **overrides):
    defaults = {
        "makerspace": makerspace,
        "name": "Loan Item",
        "total_quantity": 2,
        "available_quantity": 2,
        "is_public": True,
        "public_self_checkout_enabled": True,
    }
    defaults.update(overrides)
    return InventoryProduct.objects.create(**defaults)


def make_box_qr(makerspace, box):
    return QrCode.objects.create(
        makerspace=makerspace,
        target_type=QrCode.TargetType.BOX,
        target_id=box.id,
    )


def checkout_payload(payload):
    return {
        "payload": payload,
        "requester_name": "Box Borrower",
        "contact_email": "box-member@example.com",
        "contact_phone": "+15550101010",
        "evidence_id": _evidence("box-member@example.com", EvidencePhoto.EvidenceType.ISSUE).id,
    }

def public_checkout_url(makerspace):
    global _current_makerspace
    _current_makerspace = makerspace
    return f"/api/v1/public/{makerspace.slug}/tools/checkout"


def direct_url(makerspace):
    global _current_makerspace
    _current_makerspace = makerspace
    return f"/api/v1/admin/makerspace/{makerspace.id}/direct-loans"


def direct_payload(**overrides):
    payload = {
        "requester_name": "Direct Box Borrower",
        "contact_email": "direct-box@example.com",
        "contact_phone": "+15550101010",
        "evidence_id": _evidence("direct-box@example.com", EvidencePhoto.EvidenceType.ISSUE).id,
    }
    payload.update(overrides)
    return payload


def _evidence(identifier, evidence_type):
    assert _current_makerspace is not None
    return EvidencePhoto.objects.create(
        makerspace=_current_makerspace,
        evidence_type=evidence_type,
        object_key=f"evidence/{_current_makerspace.id}/{evidence_type}/{identifier}-{EvidencePhoto.objects.count() + 1}",
        uploaded_by=get_or_create_requester(identifier),
    )

@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_public_box_checkout_issues_mixed_asset_and_quantity_contents():
    makerspace = make_space("box-mixed-public")
    box = Box.objects.create(makerspace=makerspace, label="Mixed Box")
    individual_product = make_product(
        makerspace,
        name="Serialized Meter",
        box=box,
        tracking_mode=TrackingMode.INDIVIDUAL,
        total_quantity=1,
        available_quantity=1,
    )
    asset = InventoryAsset.objects.create(
        makerspace=makerspace,
        product=individual_product,
        box=box,
        asset_tag="MIXED-ASSET-1",
        public_self_checkout_enabled=True,
    )
    quantity_product = make_product(makerspace, name="Cable Kit", box=box)
    qr = make_box_qr(makerspace, box)

    response = APIClient().post(
        public_checkout_url(makerspace),
        checkout_payload(qr.payload),
        format="json",
    )

    assert response.status_code == 201
    assert sorted(item["product_name"] for item in response.data["items"]) == [
        "Cable Kit",
        "Serialized Meter",
    ]
    loan = PublicToolLoan.objects.get()
    assert loan.container == box
    assert loan.asset_ids == [asset.id]
    asset.refresh_from_db()
    individual_product.refresh_from_db()
    quantity_product.refresh_from_db()
    assert asset.status == InventoryAsset.Status.ISSUED
    assert individual_product.available_quantity == 0
    assert individual_product.issued_quantity == 1
    assert quantity_product.available_quantity == 1
    assert quantity_product.issued_quantity == 1


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_public_box_checkout_blocks_subsequent_direct_container_loan():
    makerspace = make_space("box-public-blocks-direct")
    box = Box.objects.create(makerspace=makerspace, label="Shared Box")
    make_product(makerspace, name="Shared Kit", box=box)
    qr = make_box_qr(makerspace, box)
    APIClient().post(public_checkout_url(makerspace), checkout_payload(qr.payload), format="json")
    admin = make_admin(makerspace)
    client = APIClient()
    client.force_authenticate(admin)

    response = client.post(
        direct_url(makerspace),
        direct_payload(container_id=box.id, items=[]),
        format="json",
    )

    assert response.status_code == 409
    assert PublicToolLoan.objects.filter(container=box, status="checked_out").count() == 1


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_direct_box_qr_loan_sets_container():
    makerspace = make_space("box-direct-qr")
    box = Box.objects.create(makerspace=makerspace, label="Direct QR Box")
    product = make_product(makerspace, name="Direct Box Kit", box=box)
    qr = make_box_qr(makerspace, box)
    admin = make_admin(makerspace)
    client = APIClient()
    client.force_authenticate(admin)

    response = client.post(
        direct_url(makerspace),
        direct_payload(qr_payloads=[qr.payload]),
        format="json",
    )

    assert response.status_code == 201
    loan = PublicToolLoan.objects.get()
    assert loan.container == box
    assert loan.qr_code == qr
    product.refresh_from_db()
    assert product.available_quantity == 1
    assert product.issued_quantity == 1


def test_box_loan_container_backfill_migration_sets_matching_box():
    makerspace = make_space("box-backfill")
    requester = User.objects.create_user(
        username="box-backfill-user",
        role=User.Role.REQUESTER,
        access_status=User.AccessStatus.ACTIVE,
    )
    box = Box.objects.create(makerspace=makerspace, label="Backfill Box")
    request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username="box-backfill-user",
        status=HardwareRequest.Status.ISSUED,
    )
    loan = PublicToolLoan.objects.create(
        makerspace=makerspace,
        request=request,
        requester=requester,
        target_type="box",
        target_id=box.id,
        target_label=box.label,
    )
    migration = importlib.import_module(
        "apps.hardware_requests.migrations.0019_backfill_box_loan_containers"
    )

    migration.backfill_box_loan_containers(apps, None)

    loan.refresh_from_db()
    assert loan.container == box



