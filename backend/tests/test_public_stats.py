from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem
from apps.hardware_requests.self_checkout_models import PublicToolLoan
from apps.inventory.models import InventoryProduct
from apps.inventory.public_stats import build_public_stats, public_display_name
from apps.makerspaces.models import Makerspace
from apps.printing.models import ManualPrintLog, PrintBucket, PrintPrinter, PrintRequest


pytestmark = pytest.mark.django_db


def make_space(slug="public-stats", *, printing=False):
    modules = ["public_inventory"]
    if printing:
        modules.append("printing")
    return Makerspace.objects.create(
        name=slug,
        slug=slug,
        public_inventory_enabled=True,
        enabled_modules=modules,
    )


def make_user(username, **overrides):
    defaults = {
        "email": f"{username}@example.com" if "@" not in username else "",
        "access_status": User.AccessStatus.ACTIVE,
    }
    defaults.update(overrides)
    return User.objects.create_user(username=username, **defaults)


def make_product(makerspace, name, **overrides):
    defaults = {
        "makerspace": makerspace,
        "name": name,
        "is_public": True,
        "is_archived": False,
        "total_quantity": 5,
        "available_quantity": 5,
    }
    defaults.update(overrides)
    return InventoryProduct.objects.create(**defaults)


def make_request_item(
    makerspace,
    product,
    username,
    *,
    display_name=None,
    quantity=1,
    returned=0,
    status=HardwareRequest.Status.ISSUED,
    requester=None,
):
    requester = requester or make_user(username)
    issued_at = timezone.now() - timedelta(days=1)
    request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=display_name or requester.username,
        status=status,
        issued_at=issued_at,
        return_due_at=issued_at + timedelta(days=7),
    )
    item = HardwareRequestItem.objects.create(
        request=request,
        product=product,
        requested_quantity=quantity,
        accepted_quantity=quantity,
        issued_quantity=quantity,
        returned_quantity=returned,
    )
    return request, item


def make_public_tool_loan(makerspace, request, requester, *, source):
    due_at = timezone.now() + timedelta(days=3)
    loan = PublicToolLoan.objects.create(
        makerspace=makerspace,
        request=request,
        requester=requester,
        target_type="product",
        target_id=request.items.first().product_id,
        target_label="hidden target label",
        status=PublicToolLoan.Status.CHECKED_OUT,
        source=source,
        due_at=due_at,
    )
    loan.checked_out_at = timezone.now() - timedelta(hours=4)
    loan.save(update_fields=["checked_out_at"])
    return loan


def test_build_public_stats_returns_exact_schema(monkeypatch):
    makerspace = make_space("stats-schema", printing=True)

    def fake_report(makerspace_id):
        assert makerspace_id == makerspace.id
        return {
            "totals": {
                "total_requests": 9,
                "pending": 1,
                "printing": 2,
                "completed": 3,
                "collected": 1,
                "failed": 1,
                "rejected": 1,
                "accepted": 4,
            },
            "printer_hours": [
                {
                    "printer_id": 10,
                    "printer_name": "Prusa MK4",
                    "hours": 6.5,
                    "completed_requests": 3,
                }
            ],
            "total_grams_used": 420.25,
            "filament_by_brand": [
                {
                    "brand": "Polymaker",
                    "grams_used": 300.25,
                    "spools": 2,
                    "spool_id": 99,
                }
            ],
            "filament_estimated_by_period": {
                "by_month": [{"period": "2026-06", "grams": 120.5, "spool_id": 99}]
            },
            "top_requesters": [{"requester_id": 1, "requester": "private"}],
            "payments": {"paid_amount": "99.00"},
        }

    monkeypatch.setattr("apps.inventory.public_stats.build_printing_report", fake_report)

    stats = build_public_stats(makerspace)

    assert set(stats) == {"printing", "hardware", "current_loans"}
    assert set(stats["printing"]) == {
        "hours_all_time",
        "hours_this_month",
        "busiest_printer",
        "grams_all_time",
        "by_brand",
        "jobs",
        "filament_trend",
    }
    assert set(stats["printing"]["busiest_printer"]) == {"name", "hours", "completed"}
    assert set(stats["printing"]["by_brand"][0]) == {"brand", "grams"}
    assert set(stats["printing"]["jobs"]) == {"completed", "status_counts", "queue"}
    assert set(stats["printing"]["jobs"]["status_counts"]) == {
        "pending",
        "printing",
        "completed",
        "collected",
        "failed",
        "rejected",
    }
    assert set(stats["printing"]["jobs"]["queue"]) == {"pending", "printing"}
    assert set(stats["printing"]["filament_trend"][0]) == {"period", "grams"}
    assert set(stats["hardware"]) == {
        "most_popular",
        "tools_out",
        "library",
        "recently_added",
    }
    assert set(stats["hardware"]["library"]) == {
        "currently_out_count",
        "library_size",
        "available_count",
    }
    assert stats["current_loans"] == []


def test_public_display_name_masks_unsafe_names_and_prefers_request_username():
    requester = make_user(
        "plainuser",
        first_name="Real",
        last_name="Name",
    )

    assert public_display_name(
        request=SimpleNamespace(requester_username="Display Name"),
        requester=requester,
    ) == "Display Name"
    assert public_display_name(
        request=SimpleNamespace(requester_username="person@example.com"),
    ) == "Member"
    assert public_display_name(
        request=SimpleNamespace(requester_username="member 9876543210"),
    ) == "Member"
    assert public_display_name(
        request=SimpleNamespace(requester_username="checkin_" + "a" * 64),
    ) == "Member"
    assert public_display_name(requester=make_user("accepted_name")) == "accepted_name"


def test_non_public_products_are_excluded_from_hardware_stats_and_current_loans():
    makerspace = make_space("stats-public-only")
    public_product = make_product(
        makerspace,
        "Public Drill",
        total_quantity=5,
        available_quantity=3,
        issued_quantity=2,
    )
    private_product = make_product(
        makerspace,
        "Private Scope",
        is_public=False,
        total_quantity=50,
        available_quantity=20,
        issued_quantity=30,
    )
    make_request_item(makerspace, public_product, "public-holder", quantity=2)
    make_request_item(makerspace, private_product, "private-holder", quantity=10)

    stats = build_public_stats(makerspace)

    assert stats["printing"] is None
    assert stats["hardware"]["most_popular"] == [
        {"name": "Public Drill", "times_lent": 1, "total_quantity_lent": 2}
    ]
    assert stats["hardware"]["tools_out"] == [
        {"name": "Public Drill", "quantity_out": 2}
    ]
    assert stats["hardware"]["library"] == {
        "currently_out_count": 2,
        "library_size": 1,
        "available_count": 3,
    }
    assert [row["name"] for row in stats["hardware"]["recently_added"]] == [
        "Public Drill"
    ]
    assert [row["item_name"] for row in stats["current_loans"]] == ["Public Drill"]


def test_printing_hours_this_month_uses_activity_dates_not_request_creation():
    makerspace = make_space("stats-printing-month", printing=True)
    bucket = PrintBucket.objects.create(makerspace=makerspace, name="PLA")
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="MK4")
    requester = make_user("month-requester")
    current = timezone.now()
    previous_month = current.replace(day=1) - timedelta(days=1)
    PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Current completion",
        status=PrintRequest.Status.COMPLETED,
        printer=printer,
        estimated_minutes=120,
        completed_at=current,
    )
    PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Old completion",
        status=PrintRequest.Status.COMPLETED,
        printer=printer,
        estimated_minutes=600,
        completed_at=previous_month,
    )
    ManualPrintLog.objects.create(
        makerspace=makerspace,
        printer=printer,
        grams_used=Decimal("10.00"),
        duration_minutes=30,
        title="Current manual log",
    )

    stats = build_public_stats(makerspace)

    assert stats["printing"]["hours_this_month"] == 2.5


def test_self_checkout_and_direct_handout_borrowers_appear_in_current_loans():
    makerspace = make_space("stats-current-loans")
    self_product = make_product(
        makerspace,
        "Logic Analyzer",
        available_quantity=4,
        issued_quantity=1,
    )
    direct_product = make_product(
        makerspace,
        "Thermal Camera",
        available_quantity=4,
        issued_quantity=1,
    )
    self_user = make_user("selfcheckout")
    direct_user = make_user("directborrower")
    self_request, _ = make_request_item(
        makerspace,
        self_product,
        "selfcheckout",
        display_name="Self Checkout",
        requester=self_user,
    )
    direct_request, _ = make_request_item(
        makerspace,
        direct_product,
        "directborrower",
        display_name="Direct Borrower",
        requester=direct_user,
    )
    make_public_tool_loan(
        makerspace,
        self_request,
        self_user,
        source=PublicToolLoan.Source.PUBLIC_SELF_CHECKOUT,
    )
    make_public_tool_loan(
        makerspace,
        direct_request,
        direct_user,
        source=PublicToolLoan.Source.ADMIN_DIRECT,
    )

    rows = build_public_stats(makerspace)["current_loans"]

    holders_by_item = {row["item_name"]: row["holder_name"] for row in rows}
    assert holders_by_item == {
        "Logic Analyzer": "Self Checkout",
        "Thermal Camera": "Direct Borrower",
    }
    assert all(set(row) == {"item_name", "holder_name", "due", "since"} for row in rows)
