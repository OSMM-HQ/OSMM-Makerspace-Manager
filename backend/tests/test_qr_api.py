import pytest
from django.db import connection
from django.test import override_settings
from rest_framework.test import APIClient

from apps.boxes.models import QrCode, QrScanEvent
from apps.accounts.models import User
from apps.inventory.models import InventoryProduct
from apps.makerspaces.models import MakerspaceMembership
from tests.return_helpers import (
    authenticated_client,
    make_accepted_request,
    make_member,
    make_product,
    make_space,
    make_user,
)

pytestmark = pytest.mark.django_db


def test_qr_scan_rejects_cross_makerspace_request():
    space_a = make_space("qr-scan-a")
    space_b = make_space("qr-scan-b")
    admin = make_member("qr-scan-admin", space_a)
    product_a = make_product(space_a)
    qr = QrCode.objects.create(
        makerspace=space_a,
        target_type=QrCode.TargetType.PRODUCT,
        target_id=product_a.id,
    )
    foreign_request = make_accepted_request(space_b, make_product(space_b), 1)

    response = authenticated_client(admin).post(
        "/api/v1/admin/qr/scan",
        {
            "payload": qr.payload,
            "context": QrScanEvent.Context.ISSUE,
            "request_id": foreign_request.id,
        },
        format="json",
    )

    assert response.status_code == 400
    assert QrScanEvent.objects.count() == 0


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_cannot_revoke_qr_with_outstanding_loan():
    makerspace = make_space("qr-revoke-loan")
    admin = make_member("qr-revoke-admin", makerspace)
    product = make_product(makerspace, public_self_checkout_enabled=True)
    qr = QrCode.objects.create(
        makerspace=makerspace,
        target_type=QrCode.TargetType.PRODUCT,
        target_id=product.id,
    )

    checkout = APIClient().post(
        f"/api/v1/public/{makerspace.slug}/tools/checkout",
        {"identifier": "member-1", "payload": qr.payload},
        format="json",
    )
    assert checkout.status_code == 201

    response = authenticated_client(admin).post(f"/api/v1/admin/qr/{qr.id}/revoke")

    assert response.status_code == 400
    qr.refresh_from_db()
    assert qr.status == QrCode.Status.ACTIVE


def test_admin_can_create_scan_and_revoke_box_qr():
    makerspace = make_space("qr-api")
    admin = make_member("qr-admin", makerspace)
    client = authenticated_client(admin)

    created = client.post(
        "/api/v1/admin/qr/boxes",
        {"makerspace_id": makerspace.id, "label": "Return Bin"},
        format="json",
    )
    qr = QrCode.objects.get(target_type=QrCode.TargetType.BOX)
    scanned = client.post(
        "/api/v1/admin/qr/scan",
        {"payload": qr.payload, "context": QrScanEvent.Context.INVENTORY_CHECK},
        format="json",
    )
    revoked = client.post(f"/api/v1/admin/qr/{qr.id}/revoke")

    assert created.status_code == 201
    assert scanned.status_code == 201
    assert scanned.data["target"]["type"] == "box"
    assert revoked.status_code == 200
    qr.refresh_from_db()
    assert qr.status == QrCode.Status.REVOKED


def test_guest_admin_cannot_manage_qr():
    makerspace = make_space("qr-deny")
    guest = make_member("qr-guest", makerspace, membership_role="guest_admin", role="guest_admin")

    response = authenticated_client(guest).post(
        "/api/v1/admin/qr/boxes",
        {"makerspace_id": makerspace.id, "label": "Denied"},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("membership_role", "global_role"),
    [
        (MakerspaceMembership.Role.INVENTORY_MANAGER, User.Role.REQUESTER),
        (MakerspaceMembership.Role.SPACE_MANAGER, User.Role.SPACE_MANAGER),
    ],
)
def test_suspended_qr_manager_cannot_manage_qr(membership_role, global_role):
    makerspace = make_space(f"qr-suspended-{membership_role}")
    user = make_member(
        f"qr-suspended-{membership_role}",
        makerspace,
        membership_role=membership_role,
        role=global_role,
    )
    user.access_status = User.AccessStatus.SUSPENDED
    user.save(update_fields=["access_status"])

    response = authenticated_client(user).post(
        "/api/v1/admin/qr/boxes",
        {"makerspace_id": makerspace.id, "label": "Denied"},
        format="json",
    )

    assert response.status_code == 403


def test_must_change_password_superadmin_cannot_manage_qr():
    makerspace = make_space("qr-password-rotate")
    superadmin = make_user(
        "qr-password-rotate-super",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
        must_change_password=True,
    )

    response = authenticated_client(superadmin).post(
        "/api/v1/admin/qr/boxes",
        {"makerspace_id": makerspace.id, "label": "Denied"},
        format="json",
    )

    assert response.status_code == 403
    assert QrCode.objects.count() == 0


def test_suspended_staff_cannot_resolve_qr():
    makerspace = make_space("qr-resolve-suspended")
    staff = make_member("qr-resolve-suspended-manager", makerspace)
    staff.access_status = User.AccessStatus.SUSPENDED
    staff.save(update_fields=["access_status"])
    product = make_product(makerspace)
    qr = QrCode.objects.create(
        makerspace=makerspace,
        target_type=QrCode.TargetType.PRODUCT,
        target_id=product.id,
    )

    response = authenticated_client(staff).post(
        "/api/v1/admin/qr/resolve",
        {"payload": qr.payload},
        format="json",
    )

    assert response.status_code == 403
    assert QrScanEvent.objects.count() == 0


def test_qr_scan_event_is_immutable_at_model_and_db():
    makerspace = make_space("qr-immutable")
    admin = make_member("qr-immutable-admin", makerspace)
    product = make_product(makerspace)
    qr = QrCode.objects.create(
        makerspace=makerspace,
        target_type=QrCode.TargetType.PRODUCT,
        target_id=product.id,
        created_by=admin,
    )
    scan = QrScanEvent.objects.create(
        makerspace=makerspace,
        qr_code=qr,
        actor=admin,
        context=QrScanEvent.Context.INVENTORY_CHECK,
    )

    with pytest.raises(RuntimeError):
        scan.save()
    if connection.vendor == "postgresql":
        with pytest.raises(Exception):
            QrScanEvent.objects.filter(pk=scan.pk).update(context=QrScanEvent.Context.REASSIGNMENT)
