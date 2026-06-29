import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.boxes.models import Box, BoxScan
from apps.evidence.models import EvidencePhoto
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem
from apps.inventory.models import InventoryProduct
from apps.makerspaces.models import Makerspace, MakerspaceMembership

pytestmark = pytest.mark.django_db


def make_user(username, role=User.Role.REQUESTER, **kw):
    return get_user_model().objects.create_user(
        username=username,
        email=f"{username}@e.com",
        role=role,
        **kw,
    )


def make_space(slug):
    return Makerspace.objects.create(name=slug, slug=slug)


def make_member(username, makerspace):
    user = make_user(
        username,
        role=User.Role.SPACE_MANAGER,
        access_status=User.AccessStatus.ACTIVE,
    )
    MakerspaceMembership.objects.create(
        user=user,
        makerspace=makerspace,
        role=MakerspaceMembership.Role.SPACE_MANAGER,
    )
    return user


def make_product(makerspace, name="Oscilloscope", **overrides):
    defaults = {
        "makerspace": makerspace,
        "name": name,
        "description": f"{name} description",
        "total_quantity": 10,
        "available_quantity": 10,
        "reserved_quantity": 0,
        "issued_quantity": 0,
        "is_public": True,
        "is_archived": False,
    }
    defaults.update(overrides)
    return InventoryProduct.objects.create(**defaults)


def make_request(makerspace, item_specs):
    requester = make_user(
        f"requester-{makerspace.slug}-{uuid.uuid4().hex[:8]}",
        access_status=User.AccessStatus.ACTIVE,
    )
    hardware_request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        status=HardwareRequest.Status.PENDING_APPROVAL,
    )
    for product, quantity in item_specs:
        HardwareRequestItem.objects.create(
            request=hardware_request,
            product=product,
            requested_quantity=quantity,
        )
    return hardware_request


def authenticated_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def accept_url(hardware_request):
    return f"/api/v1/admin/requests/{hardware_request.id}/accept"


def assign_box_url(hardware_request):
    return f"/api/v1/admin/requests/{hardware_request.id}/assign-box"


def issue_url(hardware_request):
    return f"/api/v1/admin/requests/{hardware_request.id}/issue"


def make_issue_evidence(makerspace, actor):
    return EvidencePhoto.objects.create(
        makerspace=makerspace,
        evidence_type=EvidencePhoto.EvidenceType.ISSUE,
        object_key=f"evidence/{makerspace.id}/issue/{uuid.uuid4().hex}",
        uploaded_by=actor,
    )


def test_no_payload_accepts_all_requested_units():
    makerspace = make_space("partial-default-full")
    product = make_product(makerspace, total_quantity=5, available_quantity=5)
    hardware_request = make_request(makerspace, [(product, 3)])
    admin = make_member("partial-default-admin", makerspace)

    response = authenticated_client(admin).post(accept_url(hardware_request), format="json")

    assert response.status_code == 200
    item = hardware_request.items.get()
    item.refresh_from_db()
    assert item.accepted_quantity == item.requested_quantity == 3
    product.refresh_from_db()
    assert product.available_quantity == 2
    assert product.reserved_quantity == 3


def test_partial_accept_reserves_requested_subset_and_omitted_item_defaults_full():
    makerspace = make_space("partial-subset")
    product = make_product(makerspace, total_quantity=5, available_quantity=5)
    omitted_product = make_product(
        makerspace,
        name="Logic Analyzer",
        total_quantity=5,
        available_quantity=5,
    )
    hardware_request = make_request(makerspace, [(product, 3), (omitted_product, 2)])
    item = hardware_request.items.get(product=product)
    omitted_item = hardware_request.items.get(product=omitted_product)
    admin = make_member("partial-subset-admin", makerspace)

    response = authenticated_client(admin).post(
        accept_url(hardware_request),
        {"accepted_quantities": [{"item_id": item.id, "quantity": 1}]},
        format="json",
    )

    assert response.status_code == 200
    item.refresh_from_db()
    omitted_item.refresh_from_db()
    assert item.accepted_quantity == 1
    assert omitted_item.accepted_quantity == omitted_item.requested_quantity == 2
    product.refresh_from_db()
    omitted_product.refresh_from_db()
    assert product.available_quantity == 4
    assert product.reserved_quantity == 1
    assert omitted_product.available_quantity == 3
    assert omitted_product.reserved_quantity == 2


def test_all_zero_partial_accept_returns_400_and_does_not_reserve():
    makerspace = make_space("partial-zero")
    product = make_product(makerspace, total_quantity=5, available_quantity=5)
    hardware_request = make_request(makerspace, [(product, 3)])
    item = hardware_request.items.get()
    admin = make_member("partial-zero-admin", makerspace)

    response = authenticated_client(admin).post(
        accept_url(hardware_request),
        {"accepted_quantities": [{"item_id": item.id, "quantity": 0}]},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    item.refresh_from_db()
    product.refresh_from_db()
    assert item.accepted_quantity == 0
    assert product.available_quantity == 5
    assert product.reserved_quantity == 0


def test_accept_quantity_above_requested_returns_400_and_does_not_reserve():
    makerspace = make_space("partial-too-many")
    product = make_product(makerspace, total_quantity=5, available_quantity=5)
    hardware_request = make_request(makerspace, [(product, 3)])
    item = hardware_request.items.get()
    admin = make_member("partial-too-many-admin", makerspace)

    response = authenticated_client(admin).post(
        accept_url(hardware_request),
        {"accepted_quantities": [{"item_id": item.id, "quantity": 4}]},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    item.refresh_from_db()
    product.refresh_from_db()
    assert item.accepted_quantity == 0
    assert product.available_quantity == 5
    assert product.reserved_quantity == 0


def test_accept_partial_then_issue_moves_only_accepted_units():
    makerspace = make_space("partial-lifecycle")
    product = make_product(makerspace, total_quantity=5, available_quantity=5)
    hardware_request = make_request(makerspace, [(product, 3)])
    item = hardware_request.items.get()
    admin = make_member("partial-lifecycle-admin", makerspace)
    client = authenticated_client(admin)

    accept_response = client.post(
        accept_url(hardware_request),
        {"accepted_quantities": [{"item_id": item.id, "quantity": 1}]},
        format="json",
    )
    assert accept_response.status_code == 200

    box = Box.objects.create(makerspace=makerspace, label="PL-1")
    assign_response = client.post(
        assign_box_url(hardware_request),
        {"box_code": box.code},
        format="json",
    )
    assert assign_response.status_code == 200
    assert BoxScan.objects.filter(request=hardware_request, box=box).exists()

    evidence = make_issue_evidence(makerspace, admin)
    issue_response = client.post(
        issue_url(hardware_request),
        {"evidence_id": evidence.id, "remark": "Issued partial approval."},
        format="json",
    )

    assert issue_response.status_code == 200
    hardware_request.refresh_from_db()
    item.refresh_from_db()
    product.refresh_from_db()
    assert hardware_request.status == HardwareRequest.Status.ISSUED
    assert item.requested_quantity == 3
    assert item.accepted_quantity == 1
    assert item.issued_quantity == 1
    assert product.available_quantity == 4
    assert product.reserved_quantity == 0
    assert product.issued_quantity == 1

def test_accept_rejects_unknown_item_id():
    # Stage-4 P2: a stale/cross-request item_id must 400, not silently default the
    # request's real items to full acceptance.
    makerspace = make_space("partial-unknown-item")
    product = make_product(makerspace, total_quantity=5, available_quantity=5)
    hardware_request = make_request(makerspace, [(product, 3)])
    item = hardware_request.items.get()
    admin = make_member("partial-unknown-admin", makerspace)

    response = authenticated_client(admin).post(
        accept_url(hardware_request),
        {"accepted_quantities": [{"item_id": item.id + 9999, "quantity": 1}]},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    hardware_request.refresh_from_db()
    item.refresh_from_db()
    product.refresh_from_db()
    assert hardware_request.status == "pending_approval"
    assert item.accepted_quantity == 0
    assert product.reserved_quantity == 0
