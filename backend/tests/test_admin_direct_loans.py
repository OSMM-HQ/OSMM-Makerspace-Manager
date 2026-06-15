from datetime import timedelta

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.boxes.models import QrCode
from apps.hardware_requests.models import HardwareRequest, PublicToolLoan
from apps.inventory.models import InventoryProduct
from apps.makerspaces.models import Makerspace, MakerspaceMembership

pytestmark = pytest.mark.django_db


def make_space(slug="direct-loan-space"):
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
        "name": "Bench Multimeter",
        "total_quantity": 3,
        "available_quantity": 3,
        "is_public": True,
        "public_self_checkout_enabled": True,
    }
    defaults.update(overrides)
    return InventoryProduct.objects.create(**defaults)


def authed(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def direct_url(makerspace):
    return f"/api/v1/admin/makerspace/{makerspace.id}/direct-loans"


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_admin_direct_manual_handout_and_return_logs_product():
    makerspace = make_space()
    makerspace.default_loan_days = 10
    makerspace.save(update_fields=["default_loan_days"])
    admin = make_admin(makerspace)
    product = make_product(makerspace)
    client = authed(admin)

    issued = client.post(
        direct_url(makerspace),
        {
            "identifier": "member-direct",
            "items": [{"product_id": product.id, "quantity": 2}],
        },
        format="json",
    )

    assert issued.status_code == 201
    assert issued.data["source"] == PublicToolLoan.Source.ADMIN_DIRECT
    product.refresh_from_db()
    assert product.available_quantity == 1
    assert product.issued_quantity == 2
    request = HardwareRequest.objects.get()
    assert request.status == HardwareRequest.Status.ISSUED
    assert request.issued_by == admin
    loan = PublicToolLoan.objects.get()
    assert loan.qr_code_id is None
    assert loan.due_at is not None
    assert abs((loan.due_at - loan.checked_out_at) - timedelta(days=10)) < timedelta(
        seconds=2
    )
    assert AuditLog.objects.filter(
        action="admin_direct.checked_out",
        target_type="inventory.inventoryproduct",
        target_id=str(product.id),
    ).exists()

    returned = client.post(
        f"/api/v1/admin/direct-loans/{loan.id}/return",
        {},
        format="json",
    )

    assert returned.status_code == 200
    assert returned.data["status"] == PublicToolLoan.Status.RETURNED
    product.refresh_from_db()
    assert product.available_quantity == 3
    assert product.issued_quantity == 0
    assert AuditLog.objects.filter(
        action="admin_direct.returned",
        target_type="inventory.inventoryproduct",
        target_id=str(product.id),
    ).exists()

    logs = client.get(
        "/api/v1/admin/audit-logs",
        {"target_type": "inventory.inventoryproduct", "target_id": str(product.id)},
    )
    assert logs.status_code == 200
    assert logs.data["count"] >= 2


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_admin_direct_handout_requires_opt_in_product():
    makerspace = make_space("direct-disabled")
    admin = make_admin(makerspace)
    product = make_product(makerspace, public_self_checkout_enabled=False)

    response = authed(admin).post(
        direct_url(makerspace),
        {
            "identifier": "member-direct",
            "items": [{"product_id": product.id, "quantity": 1}],
        },
        format="json",
    )

    assert response.status_code == 400
    assert PublicToolLoan.objects.count() == 0


def make_qr(makerspace, product):
    return QrCode.objects.create(
        makerspace=makerspace,
        target_type=QrCode.TargetType.PRODUCT,
        target_id=product.id,
    )


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_suspended_admin_cannot_issue_direct_loan():
    makerspace = make_space("direct-suspended")
    admin = make_admin(makerspace)
    admin.access_status = User.AccessStatus.SUSPENDED
    admin.save(update_fields=["access_status"])
    product = make_product(makerspace)

    response = authed(admin).post(
        direct_url(makerspace),
        {"identifier": "member-direct", "items": [{"product_id": product.id, "quantity": 1}]},
        format="json",
    )

    assert response.status_code == 403
    assert PublicToolLoan.objects.count() == 0
    product.refresh_from_db()
    assert product.issued_quantity == 0


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_every_qr_in_multi_qr_direct_loan_is_tracked():
    makerspace = make_space("direct-multi-qr")
    admin = make_admin(makerspace)
    product_a = make_product(makerspace, name="Soldering Iron")
    product_b = make_product(makerspace, name="Hot Air Station")
    qr_a = make_qr(makerspace, product_a)
    qr_b = make_qr(makerspace, product_b)
    client = authed(admin)

    issued = client.post(
        direct_url(makerspace),
        {"identifier": "member-direct", "qr_payloads": [qr_a.payload, qr_b.payload]},
        format="json",
    )

    assert issued.status_code == 201
    loan = PublicToolLoan.objects.get()
    # First QR holds the FK; both QRs are recorded so neither can be re-issued.
    assert loan.qr_code_id == qr_a.id
    assert sorted(loan.qr_ids) == sorted([qr_a.id, qr_b.id])

    # The second QR must now read as already checked out (the bug let it through).
    reissue = client.post(
        direct_url(makerspace),
        {"identifier": "member-direct", "qr_payloads": [qr_b.payload]},
        format="json",
    )

    assert reissue.status_code == 409
    assert PublicToolLoan.objects.count() == 1


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_direct_loan_rejects_duplicate_qr_payload():
    makerspace = make_space("direct-dup-qr")
    admin = make_admin(makerspace)
    product = make_product(makerspace, total_quantity=5, available_quantity=5)
    qr = make_qr(makerspace, product)

    response = authed(admin).post(
        direct_url(makerspace),
        {"identifier": "member-direct", "qr_payloads": [qr.payload, qr.payload]},
        format="json",
    )

    # Same QR twice must not decrement stock twice.
    assert response.status_code == 409
    assert PublicToolLoan.objects.count() == 0
    product.refresh_from_db()
    assert product.available_quantity == 5
    assert product.issued_quantity == 0


def make_guest(makerspace):
    user = User.objects.create_user(
        username=f"guest-{makerspace.slug}",
        role=User.Role.GUEST_ADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )
    MakerspaceMembership.objects.create(
        user=user,
        makerspace=makerspace,
        role=MakerspaceMembership.Role.GUEST_ADMIN,
    )
    return user


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_guest_admin_cannot_create_direct_loan():
    # Guest admins can issue accepted requests, but a direct handout has no
    # reviewed request — it must require ISSUE_DIRECT_LOAN, which they lack.
    makerspace = make_space("direct-guest-deny")
    guest = make_guest(makerspace)
    product = make_product(makerspace)

    response = authed(guest).post(
        direct_url(makerspace),
        {"identifier": "member-direct", "items": [{"product_id": product.id, "quantity": 1}]},
        format="json",
    )

    assert response.status_code == 403
    assert PublicToolLoan.objects.count() == 0


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_direct_return_rejects_self_checkout_loan():
    makerspace = make_space("direct-return-guard")
    admin = make_admin(makerspace)
    product = make_product(makerspace, public_self_checkout_enabled=True)
    qr = make_qr(makerspace, product)

    checkout = APIClient().post(
        f"/api/v1/public/{makerspace.slug}/tools/checkout",
        {"identifier": "member-x", "payload": qr.payload},
        format="json",
    )
    assert checkout.status_code == 201
    loan = PublicToolLoan.objects.get(source=PublicToolLoan.Source.PUBLIC_SELF_CHECKOUT)

    response = authed(admin).post(
        f"/api/v1/admin/direct-loans/{loan.id}/return",
        {},
        format="json",
    )

    # The admin direct-return must not touch a public self-checkout loan.
    assert response.status_code == 404
    loan.refresh_from_db()
    assert loan.status == PublicToolLoan.Status.CHECKED_OUT
