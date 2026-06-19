from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.printing.models import FilamentSpool, ManualPrintLog, PrintPrinter, PrintRequest
from tests.test_printing import (
    authenticated_client,
    make_bucket,
    make_print_manager,
    make_space,
    make_user,
)

pytestmark = pytest.mark.django_db


def manual_log_url():
    return reverse("printing:managed-manual-log-list")


def makerspace_report_url(makerspace):
    return reverse(
        "printing:makerspace-report",
        kwargs={"makerspace_id": makerspace.id},
    )


def rows(response):
    data = response.data
    return data["results"] if isinstance(data, dict) and "results" in data else data


def test_manual_print_log_create_deducts_spool_and_audits():
    makerspace = make_space("manual-log-create")
    manager = make_print_manager("manual-log-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        color="black",
        brand="Generic",
        initial_weight_grams=1000,
        remaining_weight_grams=1000,
    )

    response = authenticated_client(manager).post(
        manual_log_url(),
        {
            "makerspace_id": makerspace.id,
            "printer_id": printer.id,
            "filament_spool_id": spool.id,
            "grams_used": "74.50",
            "title": "Walk-up print",
            "note": "Staff assisted.",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["printer_name"] == "Prusa MK4"
    assert response.data["spool_label"] == "Generic PLA black"
    log = ManualPrintLog.objects.get(pk=response.data["id"])
    assert log.logged_by == manager
    assert log.grams_used == Decimal("74.50")
    spool.refresh_from_db()
    assert spool.remaining_weight_grams == Decimal("925.50")
    audit = AuditLog.objects.get(action="print.manual_logged")
    assert audit.target_id == str(log.id)
    assert audit.meta["remaining_before"] == "1000.00"
    assert audit.meta["remaining_after"] == "925.50"

    response = authenticated_client(manager).get(
        manual_log_url(),
        {"makerspace": makerspace.id},
    )

    assert response.status_code == 200
    assert [row["id"] for row in rows(response)] == [log.id]


def test_manual_print_log_rejects_overdraw():
    makerspace = make_space("manual-log-overdraw")
    manager = make_print_manager("manual-log-overdraw-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        initial_weight_grams=100,
        remaining_weight_grams=20,
    )

    response = authenticated_client(manager).post(
        manual_log_url(),
        {
            "makerspace_id": makerspace.id,
            "printer_id": printer.id,
            "filament_spool_id": spool.id,
            "grams_used": "25.00",
            "title": "Too much",
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "Filament used exceeds remaining spool weight."
    spool.refresh_from_db()
    assert spool.remaining_weight_grams == Decimal("20.00")
    assert not ManualPrintLog.objects.exists()


def test_manual_print_log_rejects_cross_printer_spool():
    makerspace = make_space("manual-log-cross-printer")
    manager = make_print_manager("manual-log-cross-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="A1")
    other_printer = PrintPrinter.objects.create(makerspace=makerspace, name="X1")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=other_printer,
        material="PETG",
        initial_weight_grams=1000,
        remaining_weight_grams=1000,
    )

    response = authenticated_client(manager).post(
        manual_log_url(),
        {
            "makerspace_id": makerspace.id,
            "printer_id": printer.id,
            "filament_spool_id": spool.id,
            "grams_used": "12.00",
            "title": "Wrong spool",
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "Filament spool is assigned to a different printer."
    spool.refresh_from_db()
    assert spool.remaining_weight_grams == Decimal("1000.00")


@pytest.mark.parametrize(
    ("printer_updates", "slug"),
    [
        ({"is_active": False}, "inactive"),
        ({"status": PrintPrinter.Status.MAINTENANCE}, "maintenance"),
    ],
)
def test_manual_print_log_rejects_inactive_or_non_active_printer(
    printer_updates,
    slug,
):
    makerspace = make_space(f"manual-log-printer-{slug}")
    manager = make_print_manager(f"manual-log-printer-{slug}-manager", makerspace)
    printer = PrintPrinter.objects.create(
        makerspace=makerspace,
        name=f"Printer {slug}",
        **printer_updates,
    )
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        initial_weight_grams=1000,
        remaining_weight_grams=1000,
    )

    response = authenticated_client(manager).post(
        manual_log_url(),
        {
            "makerspace_id": makerspace.id,
            "printer_id": printer.id,
            "filament_spool_id": spool.id,
            "grams_used": "12.00",
            "title": "Blocked printer",
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "Printer is not active."
    assert not ManualPrintLog.objects.exists()
    spool.refresh_from_db()
    assert spool.remaining_weight_grams == Decimal("1000.00")


@pytest.mark.parametrize("grams_used", ["0.00", "-1.00"])
def test_manual_print_log_rejects_non_positive_grams(grams_used):
    makerspace = make_space(f"manual-log-grams-{grams_used.replace('.', 'x')}")
    manager = make_print_manager(f"manual-log-grams-{grams_used}-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        initial_weight_grams=1000,
        remaining_weight_grams=1000,
    )

    response = authenticated_client(manager).post(
        manual_log_url(),
        {
            "makerspace_id": makerspace.id,
            "printer_id": printer.id,
            "filament_spool_id": spool.id,
            "grams_used": grams_used,
            "title": "Bad grams",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "grams_used" in response.data
    assert not ManualPrintLog.objects.exists()
    spool.refresh_from_db()
    assert spool.remaining_weight_grams == Decimal("1000.00")


def test_manual_print_log_rejects_over_bound_grams():
    makerspace = make_space("manual-log-grams-too-large")
    manager = make_print_manager("manual-log-grams-too-large-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        initial_weight_grams=1000,
        remaining_weight_grams=1000,
    )

    response = authenticated_client(manager).post(
        manual_log_url(),
        {
            "makerspace_id": makerspace.id,
            "printer_id": printer.id,
            "filament_spool_id": spool.id,
            "grams_used": "1000000.00",
            "title": "Bad grams",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "grams_used" in response.data
    assert not ManualPrintLog.objects.exists()
    spool.refresh_from_db()
    assert spool.remaining_weight_grams == Decimal("1000.00")


def test_manual_print_log_stores_duration_minutes():
    makerspace = make_space("manual-log-duration")
    manager = make_print_manager("manual-log-duration-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        initial_weight_grams=1000,
        remaining_weight_grams=1000,
    )

    response = authenticated_client(manager).post(
        manual_log_url(),
        {
            "makerspace_id": makerspace.id,
            "printer_id": printer.id,
            "filament_spool_id": spool.id,
            "grams_used": "20.00",
            "duration_minutes": 45,
            "title": "Timed print",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["duration_minutes"] == 45
    log = ManualPrintLog.objects.get(pk=response.data["id"])
    assert log.duration_minutes == 45


def test_printing_report_printer_hours_include_manual_duration():
    makerspace = make_space("manual-log-hours")
    bucket = make_bucket(makerspace)
    requester = make_user("manual-hours-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("manual-hours-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="A printer")
    manual_only = PrintPrinter.objects.create(makerspace=makerspace, name="B printer")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        initial_weight_grams=1000,
        remaining_weight_grams=900,
    )
    PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Queued print",
        quantity=1,
        status=PrintRequest.Status.COMPLETED,
        printer=printer,
        filament_spool=spool,
        estimated_minutes=60,
        filament_grams_used=Decimal("50.00"),
        completed_at=timezone.now(),
    )
    # 30 min manual added to the printer that already has 60 min of completed work -> 1.5h.
    ManualPrintLog.objects.create(
        makerspace=makerspace,
        printer=printer,
        filament_spool=spool,
        grams_used=Decimal("10.00"),
        duration_minutes=30,
        title="Manual add",
        logged_by=manager,
    )
    # 90 min manual on a printer with no completed requests -> manual-only 1.5h row.
    ManualPrintLog.objects.create(
        makerspace=makerspace,
        printer=manual_only,
        filament_spool=spool,
        grams_used=Decimal("10.00"),
        duration_minutes=90,
        title="Manual only",
        logged_by=manager,
    )

    response = authenticated_client(manager).get(makerspace_report_url(makerspace))

    assert response.status_code == 200
    hours = {row["printer_id"]: row for row in response.data["printer_hours"]}
    assert hours[printer.id]["hours"] == 1.5
    assert hours[printer.id]["completed_requests"] == 1
    assert hours[manual_only.id]["hours"] == 1.5
    assert hours[manual_only.id]["completed_requests"] == 0


def test_printing_report_merges_manual_logs_and_includes_manual_only_printers():
    makerspace = make_space("manual-log-report")
    bucket = make_bucket(makerspace)
    requester = make_user("manual-report-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("manual-report-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="A printer")
    manual_only = PrintPrinter.objects.create(makerspace=makerspace, name="B printer")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        initial_weight_grams=1000,
        remaining_weight_grams=900,
    )
    other_spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=manual_only,
        material="ABS",
        initial_weight_grams=1000,
        remaining_weight_grams=975,
    )
    PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Queued print",
        quantity=1,
        status=PrintRequest.Status.COMPLETED,
        printer=printer,
        filament_spool=spool,
        filament_grams_used=Decimal("50.00"),
        completed_at=timezone.now(),
    )
    ManualPrintLog.objects.create(
        makerspace=makerspace,
        printer=printer,
        filament_spool=spool,
        grams_used=Decimal("30.00"),
        title="Manual on existing printer",
        logged_by=manager,
    )
    ManualPrintLog.objects.create(
        makerspace=makerspace,
        printer=manual_only,
        filament_spool=other_spool,
        grams_used=Decimal("25.00"),
        title="Manual only",
        logged_by=manager,
    )

    response = authenticated_client(manager).get(makerspace_report_url(makerspace))

    assert response.status_code == 200
    assert response.data["printer_outcomes"] == [
        {
            "printer_id": printer.id,
            "printer_name": "A printer",
            "completed": 1,
            "failed": 0,
            "grams_used": 80.0,
            "manual_logs": 1,
        },
        {
            "printer_id": manual_only.id,
            "printer_name": "B printer",
            "completed": 0,
            "failed": 0,
            "grams_used": 25.0,
            "manual_logs": 1,
        },
    ]
