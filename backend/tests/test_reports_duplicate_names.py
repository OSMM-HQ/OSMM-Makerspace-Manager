"""Reports must not merge distinct products that happen to share a name (there is no
unique (makerspace, name) constraint, so this is a real correctness case)."""
import pytest

from apps.accounts.models import User
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem
from apps.operations import reports
from tests.return_helpers import (
    make_issued_request,
    make_member,
    make_product,
    make_space,
    make_user,
)

pytestmark = pytest.mark.django_db


def test_taken_items_and_most_lent_keep_same_named_products_separate():
    makerspace = make_space("dup-name-report")
    actor = make_member("dup-name-manager", makerspace)
    # Two DISTINCT products, identical name.
    first = make_product(makerspace, name="Clamp", total_quantity=10, available_quantity=10)
    second = make_product(makerspace, name="Clamp", total_quantity=10, available_quantity=10)
    make_issued_request(makerspace, actor, [(first, 2)])
    make_issued_request(makerspace, actor, [(second, 3)])

    taken = reports._taken_items(makerspace.id, aggregate=False)
    # header + one row per distinct product (not a single merged "Clamp" = 5).
    quantities = sorted(row[1] for row in taken[1:])
    assert quantities == [2, 3]

    most_lent = reports._most_lent(makerspace.id, aggregate=False)
    lent_quantities = sorted(row[2] for row in most_lent[1:])
    assert lent_quantities == [2, 3]


def test_top_borrowers_show_readable_label_not_checkin_hash():
    # Self-checkout shadow borrowers carry the privacy hash username checkin_<sha256>.
    # The top-borrowers report must surface a readable label, never the raw hash.
    makerspace = make_space("top-borrowers-hash")
    product = make_product(
        makerspace, name="Caliper", total_quantity=10, available_quantity=10
    )
    hashed = "checkin_" + ("c" * 64)
    requester = make_user(
        hashed,
        access_status=User.AccessStatus.ACTIVE,
        external_checkin_user_id="borrower-walkin@x.com",
    )
    request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=hashed,
        status=HardwareRequest.Status.ISSUED,
    )
    HardwareRequestItem.objects.create(
        request=request,
        product=product,
        requested_quantity=2,
        accepted_quantity=2,
        issued_quantity=2,
    )

    rows = reports._top_borrowers(makerspace.id, aggregate=False)
    holders = [row[0] for row in rows[1:]]
    assert holders, "expected at least one borrower row"
    assert all(not holder.startswith("checkin_") for holder in holders)
    assert "borrower-walkin@x.com" in holders


def test_top_borrowers_prefers_readable_request_username_over_external_id():
    # When Check-In returns a readable username (stored on the request) alongside a
    # hashed account username, the report must surface the readable request-level
    # username rather than falling back to the external id.
    makerspace = make_space("top-borrowers-username")
    product = make_product(
        makerspace, name="Drill", total_quantity=10, available_quantity=10
    )
    hashed = "checkin_" + ("d" * 64)
    requester = make_user(
        hashed,
        access_status=User.AccessStatus.ACTIVE,
        external_checkin_user_id="member-22@x.com",
    )
    request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username="jane.doe",
        status=HardwareRequest.Status.ISSUED,
    )
    HardwareRequestItem.objects.create(
        request=request,
        product=product,
        requested_quantity=1,
        accepted_quantity=1,
        issued_quantity=1,
    )

    rows = reports._top_borrowers(makerspace.id, aggregate=False)
    holders = [row[0] for row in rows[1:]]
    assert "jane.doe" in holders
    assert "member-22@x.com" not in holders
