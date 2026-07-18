import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.boxes.models import QrCode
from apps.evidence.models import EvidencePhoto
from apps.inventory.models import InventoryProduct
from apps.makerspaces.models import Makerspace, MakerspaceMembership, MakerspaceRole
from apps.makerspaces.waiver_services import accept_waiver, publish_waiver
from apps.presence import services as presence


pytestmark = pytest.mark.django_db


def _member(space, username, *, role="member"):
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.test",
        phone="+15550100",
        display_name=f"{username} display",
    )
    membership_role = MakerspaceRole.objects.get(makerspace=space, slug=role)
    MakerspaceMembership.objects.create(
        makerspace=space,
        user=user,
        assigned_role=membership_role,
        role="custom" if role == "member" else role,
    )
    return user


def _client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def _eligible(space, username="eligible"):
    user = _member(space, username)
    presence.start_session(user, space, 60)
    return user


def _request_body(product, **extra):
    return {"requested_for": "M4 test", "items": [{"product_id": product.id, "quantity": 1}], **extra}


def _recursive_values(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _recursive_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _recursive_values(item)
    else:
        yield str(value)


def test_request_submit_is_member_gated_and_snapshots_account_identity():
    space = Makerspace.objects.create(name="M4 request", slug="m4-request")
    product = InventoryProduct.objects.create(
        makerspace=space, name="M4 tool", total_quantity=1, available_quantity=1, is_public=True
    )
    url = f"/api/v1/public/{space.slug}/requests"
    assert APIClient().post(url, _request_body(product), format="json").status_code == 401

    user = _member(space, "m4-requester")
    response = _client(user).post(url, _request_body(product), format="json")
    assert response.status_code == 403 and response.data["code"] == "presence_required"
    presence.start_session(user, space, 60)
    from apps.hardware_requests.models import HardwareRequest

    honeypot = _client(user).post(url, {"website": "bot"}, format="json")
    assert honeypot.status_code == 201 and HardwareRequest.objects.count() == 0
    response = _client(user).post(
        url,
        _request_body(product, requester_name="forged", contact_email="forged@example.test", contact_phone="999"),
        format="json",
    )
    assert response.status_code == 201
    saved = HardwareRequest.objects.get()
    assert (saved.requester_id, saved.requester_name, saved.requester_contact_email, saved.requester_contact_phone) == (
        user.id, user.display_name, user.email, user.phone
    )
    assert not set(_recursive_values(response.data)) & {user.email, user.phone, str(user.id)}


def test_current_waiver_and_presence_are_required_before_member_request_mutates():
    space = Makerspace.objects.create(name="M4 waiver", slug="m4-waiver")
    product = InventoryProduct.objects.create(
        makerspace=space, name="M4 tool", total_quantity=1, available_quantity=1, is_public=True
    )
    user = _member(space, "m4-waiver-member")
    membership = user.makerspace_memberships.get(makerspace=space)
    publish_waiver(user, space, "Terms", "v1")
    url = f"/api/v1/public/{space.slug}/requests"
    waiver = _client(user).post(url, _request_body(product), format="json")
    assert waiver.status_code == 403 and waiver.data["code"] == "waiver_acceptance_required"
    accept_waiver(membership)
    absent = _client(user).post(url, _request_body(product), format="json")
    assert absent.status_code == 403 and absent.data["code"] == "presence_required"


def test_self_checkout_requires_member_gate_before_evidence_or_loan_creation():
    space = Makerspace.objects.create(name="M4 self", slug="m4-self")
    url = f"/api/v1/public/{space.slug}/tools/evidence-url"
    body = {"evidence_type": "issue", "content_type": "image/jpeg"}
    assert APIClient().post(url, body, format="json").status_code == 401
    outsider = User.objects.create_user(username="m4-outsider")
    denied = _client(outsider).post(url, body, format="json")
    assert denied.status_code == 403 and denied.data["code"] == "membership_required"


def test_direct_loan_requires_scoped_borrower_presence_and_waiver(monkeypatch):
    space = Makerspace.objects.create(name="M4 direct", slug="m4-direct")
    staff = _member(space, "m4-staff", role="space_manager")
    borrower = _member(space, "m4-borrower")
    product = InventoryProduct.objects.create(
        makerspace=space, name="M4 tool", total_quantity=1, available_quantity=1
    )
    evidence = EvidencePhoto.objects.create(
        makerspace=space,
        evidence_type=EvidencePhoto.EvidenceType.ISSUE,
        object_key="evidence/m4/direct.jpg",
        uploaded_by=staff,
    )
    monkeypatch.setattr("apps.evidence.storage.object_exists", lambda _key: True)
    url = f"/api/v1/admin/makerspace/{space.id}/direct-loans"
    payload = {"borrower_id": borrower.id, "evidence_id": evidence.id, "items": [{"product_id": product.id, "quantity": 1}]}
    missing = _client(staff).post(url, payload, format="json")
    assert missing.status_code == 403 and missing.data["code"] == "presence_required"
    presence.start_session(borrower, space, 60)
    created = _client(staff).post(url, payload, format="json")
    assert created.status_code == 201
