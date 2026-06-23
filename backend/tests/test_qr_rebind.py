import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.boxes.models import QrCode, QrScanEvent
from apps.evidence.models import EvidencePhoto
from apps.hardware_requests.workflow_utils import get_or_create_requester
from apps.hardware_requests.models import (
    HardwareRequest,
    PublicToolLoan,
)
from apps.inventory.models import TrackingMode
from apps.makerspaces.models import MakerspaceMembership
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

    assert hidden_source.status_code == 404
    assert hidden_destination.status_code == 404
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
        {
            "payload": qr.payload,
            "requester_name": "QR Borrower",
            "contact_email": "member-1@example.com",
            "contact_phone": "+15550101010",
                "evidence_id": _public_issue_evidence(makerspace, "member-1@example.com").id,
        },
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


def _public_issue_evidence(makerspace, identifier):
    return EvidencePhoto.objects.create(
        makerspace=makerspace,
        evidence_type=EvidencePhoto.EvidenceType.ISSUE,
        object_key=f"evidence/{makerspace.id}/issue/{identifier}-{EvidencePhoto.objects.count() + 1}",
        uploaded_by=get_or_create_requester(identifier),
    )


