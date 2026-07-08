from decimal import Decimal

import pytest

from apps.accounts.models import User
from apps.printing.models import FilamentSpool, PrintPrinter, PrintRequest
from apps.printing.reports import build_printing_report
from tests.test_printing import (
    action_url,
    authenticated_client,
    make_bucket,
    make_print_manager,
    make_request,
    make_space,
    make_user,
)

pytestmark = pytest.mark.django_db


def _accepted_request(slug="run-sheet"):
    makerspace = make_space(slug)
    bucket = make_bucket(makerspace)
    requester = make_user(f"{slug}-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager(f"{slug}-manager", makerspace)
    print_request = make_request(bucket, requester, status=PrintRequest.Status.ACCEPTED)
    printer = PrintPrinter.objects.create(
        makerspace=makerspace,
        name="Prusa MK4",
        model="MK4S",
    )
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        brand="Prusament",
        material="PLA",
        color="Galaxy Black",
        initial_weight_grams=Decimal("1000.00"),
        remaining_weight_grams=Decimal("900.00"),
    )
    return makerspace, manager, print_request, printer, spool


def _start_payload(printer, spool, **overrides):
    payload = {
        "printer_id": printer.id,
        "filament_spool_id": spool.id,
        "estimated_minutes": 90,
        "estimated_filament_grams": "25.50",
    }
    payload.update(overrides)
    return payload


def test_start_without_printer_returns_400():
    _, manager, print_request, printer, spool = _accepted_request("run-sheet-no-printer")
    payload = _start_payload(printer, spool)
    payload.pop("printer_id")

    response = authenticated_client(manager).post(
        action_url(print_request, "start"), payload, format="json"
    )

    assert response.status_code == 400
    assert "printer_id" in response.data
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.ACCEPTED


def test_start_without_spool_returns_400():
    _, manager, print_request, printer, spool = _accepted_request("run-sheet-no-spool")
    payload = _start_payload(printer, spool)
    payload.pop("filament_spool_id")

    response = authenticated_client(manager).post(
        action_url(print_request, "start"), payload, format="json"
    )

    assert response.status_code == 400
    assert "filament_spool_id" in response.data
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.ACCEPTED


@pytest.mark.parametrize(
    "field",
    ["estimated_minutes", "estimated_filament_grams"],
)
def test_start_without_estimates_returns_400(field):
    _, manager, print_request, printer, spool = _accepted_request(f"run-sheet-no-{field}")
    payload = _start_payload(printer, spool)
    payload.pop(field)

    response = authenticated_client(manager).post(
        action_url(print_request, "start"), payload, format="json"
    )

    assert response.status_code == 400
    assert field in response.data
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.ACCEPTED


def test_successful_start_persists_run_sheet_snapshot():
    _, manager, print_request, printer, spool = _accepted_request("run-sheet-start")

    response = authenticated_client(manager).post(
        action_url(print_request, "start"),
        _start_payload(printer, spool),
        format="json",
    )

    assert response.status_code == 200
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.PRINTING
    assert print_request.run_printer_name == "Prusa MK4"
    assert print_request.run_printer_model == "MK4S"
    assert print_request.run_spool_label == "Prusament PLA Galaxy Black"
    assert print_request.run_spool_material == "PLA"
    assert print_request.run_spool_color == "Galaxy Black"
    assert print_request.run_estimated_minutes == 90
    assert print_request.run_planned_filament_grams == Decimal("25.50")


def test_printer_and_spool_edits_after_start_do_not_change_snapshot():
    _, manager, print_request, printer, spool = _accepted_request("run-sheet-immutable")
    response = authenticated_client(manager).post(
        action_url(print_request, "start"),
        _start_payload(printer, spool),
        format="json",
    )
    assert response.status_code == 200

    printer.name = "Renamed Printer"
    printer.model = "Changed Model"
    printer.save(update_fields=["name", "model", "updated_at"])
    spool.material = "PETG"
    spool.color = "Orange"
    spool.brand = "Changed Brand"
    spool.save(update_fields=["material", "color", "brand", "updated_at"])

    print_request.refresh_from_db()
    assert print_request.run_printer_name == "Prusa MK4"
    assert print_request.run_printer_model == "MK4S"
    assert print_request.run_spool_label == "Prusament PLA Galaxy Black"
    assert print_request.run_spool_material == "PLA"
    assert print_request.run_spool_color == "Galaxy Black"


def test_report_uses_run_sheet_snapshot_values_after_live_edits():
    makerspace, manager, print_request, printer, spool = _accepted_request("run-sheet-report")
    response = authenticated_client(manager).post(
        action_url(print_request, "start"),
        _start_payload(printer, spool),
        format="json",
    )
    assert response.status_code == 200

    printer.name = "Renamed Printer"
    printer.save(update_fields=["name", "updated_at"])
    spool.material = "PETG"
    spool.color = "Orange"
    spool.save(update_fields=["material", "color", "updated_at"])
    print_request.estimated_minutes = 999
    print_request.estimated_filament_grams = Decimal("99.00")
    print_request.save(update_fields=["estimated_minutes", "estimated_filament_grams", "updated_at"])

    response = authenticated_client(manager).post(
        action_url(print_request, "complete"), format="json"
    )
    assert response.status_code == 200

    report = build_printing_report(makerspace.id)

    assert report["printer_hours"] == [
        {
            "printer_id": printer.id,
            "printer_name": "Prusa MK4",
            "printer_model": "MK4S",
            "image_url": None,
            "completed_requests": 1,
            "hours": 1.5,
        }
    ]
    assert report["filament_estimated_by_period"]["by_month"][0]["grams"] == 25.5

