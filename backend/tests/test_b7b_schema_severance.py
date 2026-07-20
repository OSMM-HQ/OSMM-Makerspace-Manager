import importlib

import pytest
from django.db import IntegrityError, transaction

from apps.inventory.models import InventoryAsset
from apps.machines.models import Machine, MachineType
from apps.makerspaces.models import Makerspace
from apps.warranty.models import Warranty
from tests.return_helpers import make_product
from tests.return_helpers import make_space


pytestmark = pytest.mark.django_db


def test_warranty_has_only_asset_or_machine_hosts():
    makerspace = make_space("b7b-warranty-host")
    machine = Machine.objects.create(
        makerspace=makerspace,
        machine_type=MachineType.objects.get(makerspace__isnull=True, slug="3d_printer"),
        name="Kernel printer",
    )
    asset = InventoryAsset.objects.create(
        makerspace=makerspace,
        product=make_product(makerspace),
        asset_tag="B7B-1",
    )

    warranty = Warranty.objects.create(makerspace=makerspace, machine=machine)
    assert warranty.machine == machine
    assert not hasattr(Warranty, "printer")
    with pytest.raises(IntegrityError), transaction.atomic():
        Warranty.objects.create(makerspace=makerspace)
    with pytest.raises(IntegrityError), transaction.atomic():
        Warranty.objects.create(makerspace=makerspace, asset=asset, machine=machine)


def test_machine_printer_bridge_modules_are_gone():
    assert not hasattr(Machine, "linked_print_printer")
    for module in ("apps.machines.signals", "apps.machines.linking"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module)