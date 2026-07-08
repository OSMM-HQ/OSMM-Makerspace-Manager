from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.audit.models import AuditLog
from apps.printing import services_manual_logs
from apps.printing.models import FilamentSpool, PrintPrinter
from apps.printing.spool_reservations import reserve_filament
from apps.procurement.models import ToBuyItem
from tests.test_printing import (
    make_bucket,
    make_print_manager,
    make_request,
    make_space,
    make_user,
)

pytestmark = pytest.mark.django_db


def _setup(slug, *, threshold="0.00", remaining="1000.00"):
    makerspace = make_space(slug)
    makerspace.filament_low_stock_threshold_grams = Decimal(threshold)
    makerspace.save(update_fields=["filament_low_stock_threshold_grams"])
    bucket = make_bucket(makerspace)
    requester = make_user(f"{slug}-requester", access_status="active")
    manager = make_print_manager(f"{slug}-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        color="black",
        brand="Generic",
        initial_weight_grams=Decimal("1000.00"),
        remaining_weight_grams=Decimal(remaining),
    )
    return makerspace, bucket, requester, manager, printer, spool


def _reserve(bucket, requester, manager, spool, grams):
    print_request = make_request(bucket, requester)
    print_request.filament_spool = spool
    print_request.estimated_filament_grams = Decimal(grams)
    reserve_filament(manager, print_request)
    spool.refresh_from_db()
    return print_request


def _low_stock_items(spool):
    return ToBuyItem.objects.filter(source_spool=spool).order_by("id")


def test_threshold_zero_leaves_low_stock_automation_off():
    _, bucket, requester, manager, _, spool = _setup(
        "low-stock-off",
        threshold="0.00",
    )

    _reserve(bucket, requester, manager, spool, "950.00")

    assert spool.remaining_weight_grams == Decimal("50.00")
    assert not ToBuyItem.objects.exists()
    assert not AuditLog.objects.filter(action="procurement.low_stock_flagged").exists()


def test_drop_to_threshold_creates_one_printing_to_buy_item_for_spool():
    makerspace, bucket, requester, manager, _, spool = _setup(
        "low-stock-create",
        threshold="100.00",
    )

    _reserve(bucket, requester, manager, spool, "900.00")

    item = ToBuyItem.objects.get()
    assert item.makerspace == makerspace
    assert item.kind == ToBuyItem.Kind.PRINTING
    assert item.status == ToBuyItem.Status.REQUESTED
    assert item.source_spool == spool
    assert item.created_by == manager
    assert item.name == "Filament restock: PLA black"
    audit = AuditLog.objects.get(action="procurement.low_stock_flagged")
    assert audit.makerspace == makerspace
    assert audit.meta["spool_id"] == spool.id
    assert audit.meta["remaining"] == "100.00"
    assert audit.meta["threshold"] == "100.00"
    assert audit.meta["to_buy_item_id"] == item.id


def test_second_deduction_while_item_open_does_not_duplicate():
    _, bucket, requester, manager, _, spool = _setup(
        "low-stock-dedupe",
        threshold="200.00",
    )

    _reserve(bucket, requester, manager, spool, "850.00")
    _reserve(bucket, requester, manager, spool, "25.00")

    assert _low_stock_items(spool).count() == 1


@pytest.mark.parametrize("closed_status", [ToBuyItem.Status.RECEIVED, ToBuyItem.Status.CANCELLED])
def test_closed_auto_item_allows_future_low_stock_flag(closed_status):
    _, bucket, requester, manager, _, spool = _setup(
        f"low-stock-reopen-{closed_status}",
        threshold="200.00",
    )
    _reserve(bucket, requester, manager, spool, "850.00")
    first = _low_stock_items(spool).get()
    first.status = closed_status
    first.save(update_fields=["status", "updated_at"])

    _reserve(bucket, requester, manager, spool, "25.00")

    assert list(_low_stock_items(spool).values_list("status", flat=True)) == [
        closed_status,
        ToBuyItem.Status.REQUESTED,
    ]


def test_low_stock_helper_failure_does_not_roll_back_manual_print_log():
    _, _, _, manager, printer, spool = _setup(
        "low-stock-failsafe",
        threshold="950.00",
    )

    with patch(
        "apps.printing.low_stock.ToBuyItem.objects.create",
        side_effect=RuntimeError("procurement unavailable"),
    ):
        log = services_manual_logs.log_manual_print(
            manager,
            spool.makerspace,
            printer,
            spool,
            Decimal("75.00"),
            "Walk-up print",
            "",
        )

    spool.refresh_from_db()
    assert log.pk is not None
    assert spool.remaining_weight_grams == Decimal("925.00")
    assert not ToBuyItem.objects.exists()


def test_auto_item_uses_spool_tenant_even_with_actor_from_other_space():
    other_space = make_space("low-stock-other")
    other_actor = make_print_manager("low-stock-other-manager", other_space)
    makerspace, bucket, requester, _, _, spool = _setup(
        "low-stock-tenant",
        threshold="100.00",
    )

    _reserve(bucket, requester, other_actor, spool, "900.00")

    item = ToBuyItem.objects.get()
    assert item.makerspace == makerspace
    assert item.kind == ToBuyItem.Kind.PRINTING
    assert item.source_spool == spool