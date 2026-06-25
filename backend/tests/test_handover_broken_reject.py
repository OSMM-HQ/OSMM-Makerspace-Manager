"""Per-item broken-reject at handover + the to-be-fixed shelf (repair/scrap)."""
from unittest.mock import Mock

import pytest

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.hardware_requests.models import HardwareRequest
from apps.inventory.models import TrackingMode
from tests.test_issue import (
    active_loans_url,  # noqa: F401  (kept for parity / future use)
    assign_scanned_box,
    authenticated_client,
    issue_url,
    make_box,
    make_accepted_request,
    make_issue_evidence,
    make_member,
    make_product,
    make_space,
    make_user,
)

pytestmark = pytest.mark.django_db


def _ready_request(makerspace, admin, qty, **product_kw):
    product = make_product(makerspace, total_quantity=qty, available_quantity=qty, **product_kw)
    request = make_accepted_request(makerspace, product, qty)
    assign_scanned_box(request, make_box(makerspace), admin)
    return product, request


def test_issue_rejects_broken_to_needs_fix_shelf(monkeypatch):
    makerspace = make_space("reject-needsfix")
    admin = make_member("reject-needsfix-admin", makerspace)
    product, request = _ready_request(makerspace, admin, 3)
    evidence = make_issue_evidence(makerspace, admin)
    monkeypatch.setattr("apps.evidence.storage.object_exists", Mock(return_value=True))

    item = request.items.get()
    response = authenticated_client(admin).post(
        issue_url(request),
        {
            "evidence_id": evidence.id,
            "remark": "One unit cracked.",
            "rejects": [{"item_id": item.id, "broken": 1, "disposition": "needs_fix"}],
        },
        format="json",
    )

    assert response.status_code == 200
    request.refresh_from_db()
    assert request.status == HardwareRequest.Status.ISSUED
    product.refresh_from_db()
    assert product.issued_quantity == 2
    assert product.needs_fix_quantity == 1
    assert product.reserved_quantity == 0
    assert product.total_quantity == 3  # nothing left inventory; the broken unit is shelved
    item.refresh_from_db()
    assert item.issued_quantity == 2
    assert item.needs_fix_quantity == 1


def test_issue_rejects_broken_removed_from_inventory(monkeypatch):
    makerspace = make_space("reject-remove")
    admin = make_member("reject-remove-admin", makerspace)
    product, request = _ready_request(makerspace, admin, 3)
    evidence = make_issue_evidence(makerspace, admin)
    monkeypatch.setattr("apps.evidence.storage.object_exists", Mock(return_value=True))

    item = request.items.get()
    response = authenticated_client(admin).post(
        issue_url(request),
        {
            "evidence_id": evidence.id,
            "rejects": [{"item_id": item.id, "broken": 1, "disposition": "remove"}],
        },
        format="json",
    )

    assert response.status_code == 200
    product.refresh_from_db()
    assert product.issued_quantity == 2
    assert product.needs_fix_quantity == 0
    assert product.total_quantity == 2  # scrapped unit left inventory entirely
    item.refresh_from_db()
    assert item.needs_fix_quantity == 0


def test_broken_reject_on_individual_item_returns_400(monkeypatch):
    makerspace = make_space("reject-individual")
    admin = make_member("reject-individual-admin", makerspace)
    product, request = _ready_request(
        makerspace, admin, 2, tracking_mode=TrackingMode.INDIVIDUAL
    )
    evidence = make_issue_evidence(makerspace, admin)
    monkeypatch.setattr("apps.evidence.storage.object_exists", Mock(return_value=True))

    item = request.items.get()
    response = authenticated_client(admin).post(
        issue_url(request),
        {
            "evidence_id": evidence.id,
            "rejects": [{"item_id": item.id, "broken": 1}],
        },
        format="json",
    )

    assert response.status_code == 400
    product.refresh_from_db()
    assert product.needs_fix_quantity == 0


def _shelf_url():
    return "/api/v1/admin/inventory/needs-fix"


def _shelf_action_url(product):
    return f"/api/v1/admin/inventory/{product.id}/needs-fix"


def test_needs_fix_shelf_lists_and_repairs():
    makerspace = make_space("shelf-repair")
    admin = make_member("shelf-repair-admin", makerspace)
    product = make_product(
        makerspace, total_quantity=5, available_quantity=3, needs_fix_quantity=2
    )
    client = authenticated_client(admin)

    listing = client.get(f"{_shelf_url()}?makerspace={makerspace.id}")
    assert listing.status_code == 200
    assert [row["id"] for row in listing.data["results"]] == [product.id]

    repaired = client.post(
        _shelf_action_url(product), {"action": "repair", "quantity": 2}, format="json"
    )
    assert repaired.status_code == 200
    product.refresh_from_db()
    assert product.needs_fix_quantity == 0
    assert product.available_quantity == 5
    assert product.total_quantity == 5


def test_needs_fix_shelf_shelves_available_units():
    makerspace = make_space("shelf-move-to-fix")
    admin = make_member("shelf-move-to-fix-admin", makerspace)
    product = make_product(
        makerspace, total_quantity=5, available_quantity=4, needs_fix_quantity=0
    )

    response = authenticated_client(admin).post(
        _shelf_action_url(product), {"action": "shelve", "quantity": 2}, format="json"
    )

    assert response.status_code == 200
    product.refresh_from_db()
    assert product.available_quantity == 2
    assert product.needs_fix_quantity == 2
    assert product.total_quantity == 5
    assert AuditLog.objects.filter(action="inventory.needs_fix_shelve").exists()


def test_needs_fix_shelve_over_available_returns_400():
    makerspace = make_space("shelf-move-to-fix-overdraw")
    admin = make_member("shelf-move-to-fix-overdraw-admin", makerspace)
    product = make_product(
        makerspace, total_quantity=5, available_quantity=1, needs_fix_quantity=0
    )

    response = authenticated_client(admin).post(
        _shelf_action_url(product), {"action": "shelve", "quantity": 2}, format="json"
    )

    assert response.status_code == 400
    product.refresh_from_db()
    assert product.available_quantity == 1
    assert product.needs_fix_quantity == 0

def test_superadmin_needs_fix_shelf_hides_disabled_space_unless_explicit():
    visible_space = make_space("shelf-visible-superadmin")
    hidden_space = make_space("shelf-hidden-superadmin")
    make_member("shelf-hidden-superadmin-manager", hidden_space)
    hidden_space.superadmin_access_enabled = False
    hidden_space.save(update_fields=["superadmin_access_enabled"])
    visible_product = make_product(
        visible_space,
        name="Visible fix",
        total_quantity=2,
        available_quantity=1,
        needs_fix_quantity=1,
    )
    hidden_product = make_product(
        hidden_space,
        name="Hidden fix",
        total_quantity=2,
        available_quantity=1,
        needs_fix_quantity=1,
    )
    superadmin = make_user(
        "shelf-hidden-superadmin",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )
    client = authenticated_client(superadmin)

    listing = client.get(_shelf_url())
    assert listing.status_code == 200
    assert {row["id"] for row in listing.data["results"]} == {visible_product.id}

    # Hard hide: even an explicit ?makerspace=<hidden id> yields nothing for a
    # global superadmin (the soft-hide escape hatch is closed by the RBAC block).
    listing = client.get(_shelf_url(), {"makerspace": hidden_space.id})
    assert listing.status_code == 200
    assert {row["id"] for row in listing.data["results"]} == set()


def test_needs_fix_shelf_scrap_drops_total():
    makerspace = make_space("shelf-scrap")
    admin = make_member("shelf-scrap-admin", makerspace)
    product = make_product(
        makerspace, total_quantity=5, available_quantity=3, needs_fix_quantity=2
    )

    response = authenticated_client(admin).post(
        _shelf_action_url(product), {"action": "scrap", "quantity": 1}, format="json"
    )

    assert response.status_code == 200
    product.refresh_from_db()
    assert product.needs_fix_quantity == 1
    assert product.total_quantity == 4
    assert product.available_quantity == 3


def test_needs_fix_repair_over_shelf_count_returns_400():
    makerspace = make_space("shelf-overrepair")
    admin = make_member("shelf-overrepair-admin", makerspace)
    product = make_product(
        makerspace, total_quantity=5, available_quantity=4, needs_fix_quantity=1
    )

    response = authenticated_client(admin).post(
        _shelf_action_url(product), {"action": "repair", "quantity": 5}, format="json"
    )

    assert response.status_code == 400
    product.refresh_from_db()
    assert product.needs_fix_quantity == 1
