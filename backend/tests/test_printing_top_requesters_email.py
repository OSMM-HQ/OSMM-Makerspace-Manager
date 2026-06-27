from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.printing.models import PrintRequest
from apps.printing.reports import build_printing_report
from tests.test_printing import make_bucket, make_space, make_user

pytestmark = pytest.mark.django_db


def _completed(bucket, requester, grams, *, email="", name=""):
    return PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Print",
        quantity=1,
        status=PrintRequest.Status.COMPLETED,
        contact_email=email,
        requester_name=name,
        estimated_filament_grams=Decimal(grams),
        completed_at=timezone.now(),
    )


def test_top_requesters_group_by_email_show_name():
    makerspace = make_space("topreq-email")
    bucket = make_bucket(makerspace)
    u1 = make_user("topreq-u1", access_status=User.AccessStatus.ACTIVE)
    u2 = make_user("topreq-u2", access_status=User.AccessStatus.ACTIVE)
    # Same person (same email), two distinct shadow-user rows + a case difference.
    _completed(bucket, u1, "10.00", email="Alice@Example.com", name="Alice")
    _completed(bucket, u2, "15.00", email="alice@example.com", name="Alice")

    rows = build_printing_report(makerspace.id)["top_requesters"]

    assert len(rows) == 1
    assert rows[0]["requester"] == "Alice"   # name, not email/username
    assert rows[0]["grams"] == 25.0          # collapsed across both rows
    assert rows[0]["requests"] == 2


def test_top_requesters_blank_email_uses_legacy_label():
    makerspace = make_space("topreq-legacy")
    bucket = make_bucket(makerspace)
    u = make_user("topreq-legacy-user", access_status=User.AccessStatus.ACTIVE)
    _completed(bucket, u, "5.00")  # contact_email defaults to ""

    rows = build_printing_report(makerspace.id)["top_requesters"]

    assert len(rows) == 1
    assert rows[0]["requester"]  # non-empty legacy label
    assert rows[0]["grams"] == 5.0
