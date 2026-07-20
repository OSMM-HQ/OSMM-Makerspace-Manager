"""B4 cutover gates: provenance idempotency, mismatch stop, and authority fence."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.machines.models import MachineServiceRequest, PrintingCutoverRepair
from apps.machines.printing_cutover import CutoverMismatch, backfill, flip_authority, kernel_is_authoritative
from apps.printing.models import FilamentSpool, PrintBucket, PrintPrinter, PrintRequest
from tests.return_helpers import make_space, make_user


pytestmark = pytest.mark.django_db


def _legacy_space(slug):
    space, user = make_space(slug), make_user(f"{slug}-requester")
    bucket = PrintBucket.objects.create(makerspace=space, name="Print queue")
    printer = PrintPrinter.objects.create(makerspace=space, name="MK4", model="Prusa MK4")
    spool = FilamentSpool.objects.create(
        makerspace=space, printer=printer, material="PLA", color="Blue",
        initial_weight_grams=Decimal("100"), remaining_weight_grams=Decimal("100"),
    )
    request = PrintRequest.objects.create(
        bucket=bucket, requester=user, title="Bracket", material="PLA", color="Blue", quantity=1,
        requested_filament_spool=spool,
    )
    return space, user, bucket, printer, spool, request


def test_backfill_is_idempotent_and_flip_makes_legacy_read_only():
    space, user, _, _, _, legacy = _legacy_space("b4-idempotent")
    first, second = backfill(space), backfill(space)
    assert first.pk == second.pk
    kernel = MachineServiceRequest.objects.get(legacy_print_request_id=legacy.pk)
    assert kernel.public_token == legacy.public_token
    assert MachineServiceRequest.objects.filter(makerspace=space).count() == 1

    flip_authority(space)
    assert kernel_is_authoritative(space)
    with pytest.raises(ValidationError, match="read-only"):
        PrintRequest.objects.create(bucket=legacy.bucket, requester=user, title="Forbidden")


def test_reconciliation_stops_and_records_a_forward_repair():
    space, _, _, _, spool, _ = _legacy_space("b4-mismatch")
    spool.remaining_weight_grams = Decimal("90")
    spool.save(update_fields=["remaining_weight_grams"])
    with pytest.raises(CutoverMismatch, match="Ledger balance"):
        backfill(space)
    assert PrintingCutoverRepair.objects.filter(
        makerspace=space, kind="mismatch", legacy_model="machines.printing_cutover"
    ).exists()
