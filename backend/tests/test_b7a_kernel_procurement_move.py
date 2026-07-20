"""B7a procurement conversion follows the printing cutover authority boundary."""

from decimal import Decimal

import pytest
from rest_framework.exceptions import ValidationError

from apps.machines.models import Machine, MachineConsumablePool
from apps.machines.printing_cutover import flip_authority
from apps.printing.models import FilamentSpool, PrintPrinter
from apps.procurement.models import ToBuyItem
from apps.procurement.services import move_to_printing
from tests.test_printing import make_space, make_user


pytestmark = pytest.mark.django_db


def _received_item(makerspace, name):
    return ToBuyItem.objects.create(
        makerspace=makerspace, kind=ToBuyItem.Kind.PRINTING, name=name, status=ToBuyItem.Status.RECEIVED,
    )


def test_procurement_move_uses_kernel_when_flipped_and_legacy_models_when_unflipped():
    makerspace = make_space("b7a-procurement-kernel")
    flip_authority(makerspace)
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

    legacy_space = make_space("b7a-procurement-legacy")
    legacy_actor = make_user("b7a-procurement-legacy-actor")
    legacy_printer = move_to_printing(
        legacy_actor, _received_item(legacy_space, "Printer"), target="printer",
        data={"name": "Legacy MK4", "model": "MK4", "status": "active"},
    )
    legacy_spool = move_to_printing(
        legacy_actor, _received_item(legacy_space, "PLA spool"), target="spool",
        data={"printer": legacy_printer.id, "material": "PLA", "color": "Blue", "brand": "MakerFil",
              "initial_weight_grams": "1000.00", "remaining_weight_grams": "900.00"},
    )
    assert isinstance(legacy_printer, PrintPrinter)
    assert isinstance(legacy_spool, FilamentSpool)
    assert (legacy_spool.printer, legacy_spool.initial_weight_grams, legacy_spool.remaining_weight_grams) == (
        legacy_printer, Decimal("1000.00"), Decimal("900.00"),
    )
    assert not Machine.objects.filter(makerspace=legacy_space).exists()
    assert not MachineConsumablePool.objects.filter(makerspace=legacy_space).exists()


def test_kernel_procurement_move_validates_pool_material_and_weights():
    makerspace = make_space("b7a-procurement-kernel-validation")
    flip_authority(makerspace)
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
