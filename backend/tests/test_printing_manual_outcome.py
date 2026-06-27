from decimal import Decimal

import pytest
from django.urls import reverse

from apps.printing.models import FilamentSpool, ManualPrintLog, PrintPrinter
from apps.printing.reports import build_printing_report
from tests.test_printing import (
    authenticated_client,
    make_print_manager,
    make_space,
)

pytestmark = pytest.mark.django_db


def manual_log_url():
    return reverse("printing:managed-manual-log-list")


def _setup(slug):
    makerspace = make_space(slug)
    manager = make_print_manager(f"{slug}-mgr", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Rig")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        color="black",
        brand="Generic",
        initial_weight_grams=1000,
        remaining_weight_grams=1000,
    )
    return makerspace, manager, printer, spool


def _payload(makerspace, printer, spool, **overrides):
    payload = {
        "makerspace_id": makerspace.id,
        "printer_id": printer.id,
        "filament_spool_id": spool.id,
        "grams_used": "20.00",
        "duration_minutes": 100,
        "title": "Walk-up print",
    }
    payload.update(overrides)
    return payload


def test_manual_failed_log_persists_outcome_percent_reason():
    makerspace, manager, printer, spool = _setup("manual-failed")
    response = authenticated_client(manager).post(
        manual_log_url(),
        _payload(
            makerspace, printer, spool,
            outcome="failed", percent_complete=40, reason="Clog at layer 5",
        ),
        format="json",
    )
    assert response.status_code == 201
    log = ManualPrintLog.objects.get(pk=response.data["id"])
    assert log.outcome == ManualPrintLog.Outcome.FAILED
    assert log.percent_complete == 40
    assert log.reason == "Clog at layer 5"


def test_manual_failed_log_requires_reason():
    makerspace, manager, printer, spool = _setup("manual-failed-noreason")
    response = authenticated_client(manager).post(
        manual_log_url(),
        _payload(makerspace, printer, spool, outcome="failed", percent_complete=40),
        format="json",
    )
    assert response.status_code == 400


def test_manual_success_forces_full_percent_and_blank_reason():
    makerspace, manager, printer, spool = _setup("manual-success")
    response = authenticated_client(manager).post(
        manual_log_url(),
        _payload(
            makerspace, printer, spool,
            outcome="success", percent_complete=30, reason="ignored",
        ),
        format="json",
    )
    assert response.status_code == 201
    log = ManualPrintLog.objects.get(pk=response.data["id"])
    assert log.outcome == ManualPrintLog.Outcome.SUCCESS
    assert log.percent_complete == 100
    assert log.reason == ""


def test_failed_manual_log_counts_partial_hours_and_failed_tally():
    makerspace, manager, printer, spool = _setup("manual-report")
    # 100 min at 50% -> 50 min partial.
    authenticated_client(manager).post(
        manual_log_url(),
        _payload(
            makerspace, printer, spool,
            duration_minutes=100, outcome="failed", percent_complete=50,
            reason="snapped",
        ),
        format="json",
    )
    report = build_printing_report(makerspace.id)
    hours = {r["printer_id"]: r for r in report["printer_hours"]}
    outcomes = {r["printer_id"]: r for r in report["printer_outcomes"]}

    assert hours[printer.id]["hours"] == round(50 / 60, 1)
    assert outcomes[printer.id]["failed"] == 1
    assert outcomes[printer.id]["manual_logs"] == 1
