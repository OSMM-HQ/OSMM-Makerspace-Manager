"""Reports must not merge distinct products that happen to share a name (there is no
unique (makerspace, name) constraint, so this is a real correctness case)."""
import pytest

from apps.operations import reports
from tests.return_helpers import (
    make_issued_request,
    make_member,
    make_product,
    make_space,
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
