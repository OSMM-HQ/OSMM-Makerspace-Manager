"""B7b procurement conversion is kernel-only for every makerspace."""

from decimal import Decimal

import pytest
from rest_framework.exceptions import ValidationError

from apps.machines.models import Machine, MachineConsumablePool
from apps.printing.models import FilamentSpool, PrintPrinter
from apps.procurement.models import ToBuyItem
from apps.procurement.services import move_to_printing
from tests.test_printing import make_space, make_user


pytestmark = pytest.mark.django_db


def _received_item(makerspace, name):
    return ToBuyItem.objects.create(
        makerspace=makerspace, kind=ToBuyItem.Kind.PRINTING, name=name, status=ToBuyItem.Status.RECEIVED,
    )


def test_procurement_move_always_uses_kernel_and_records_kernel_destinations():
    makerspace = make_space("b7a-procurement-kernel")
    actor = make_user("b7a-procurement-kernel-actor")
    printer = move_to_printing(
        actor, _received_item(makerspace, "Printer"), target="printer",
        data={"name": "Kernel MK4", "model": "MK4", "status": "active"},
    )
    pool = move_to_printing(
        actor, _received_item(makerspace, "PLA spool"), target="spool",
        data={"printer": printer.id, "material": "PLA", "color": "Blue", "brand": "MakerFil",
              "initial_weight_grams": "1000.00", "remaining_weight_grams": "900.00"},
    )
    pool.refresh_from_db()
    assert isinstance(printer, Machine)
    assert (printer.machine_type.slug, printer.type_payload) == ("3d_printer", {"model": "MK4"})
    assert isinstance(pool, MachineConsumablePool)
    assert (pool.machine, pool.initial_grams, pool.remaining_grams) == (printer, Decimal("1000.00"), Decimal("900.00"))
    assert not PrintPrinter.objects.filter(makerspace=makerspace).exists()
    assert not FilamentSpool.objects.filter(makerspace=makerspace).exists()

    printer_item = ToBuyItem.objects.get(name="Printer")
    pool_item = ToBuyItem.objects.get(name="PLA spool")
    assert printer_item.resulting_machine == printer
    assert pool_item.resulting_pool == pool

    other_space = make_space("b7b-procurement-kernel")
    other_printer = move_to_printing(
        make_user("b7b-procurement-kernel-actor"), _received_item(other_space, "Other Printer"),
        target="printer", data={"name": "Other MK4", "model": "MK4"},
    )
    assert isinstance(other_printer, Machine)
    assert not MachineConsumablePool.objects.filter(makerspace=other_space).exists()

def test_kernel_procurement_move_validates_pool_material_and_weights():
    makerspace = make_space("b7a-procurement-kernel-validation")
    actor = make_user("b7a-procurement-kernel-validation-actor")

    with pytest.raises(ValidationError) as blank_material:
        move_to_printing(
            actor, _received_item(makerspace, "Blank material"), target="spool",
            data={"material": "  ", "initial_weight_grams": "100"},
        )
    assert blank_material.value.detail == {"material": "This field is required."}

    with pytest.raises(ValidationError) as negative_initial:
        move_to_printing(
            actor, _received_item(makerspace, "Negative initial"), target="spool",
            data={"material": "PLA", "initial_weight_grams": "-1"},
        )
    assert negative_initial.value.detail == {
        "initial_weight_grams": "Must be zero or greater.",
    }
