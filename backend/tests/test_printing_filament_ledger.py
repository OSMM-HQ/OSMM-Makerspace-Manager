from decimal import Decimal

import pytest
from django.db.models import Sum
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.printing import services_manual_logs, workflow
from apps.printing.models import FilamentAdjustment, FilamentSpool, PrintPrinter
from tests.test_printing import (
    authenticated_client,
    make_bucket,
    make_print_manager,
    make_request,
    make_space,
    make_user,
)

pytestmark = pytest.mark.django_db


def makerspace_report_url(makerspace):
    return reverse("printing:makerspace-report", kwargs={"makerspace_id": makerspace.id})


def spool_adjustment_url(spool):
    return reverse("printing:managed-spool-adjustment", kwargs={"pk": spool.id})


def _setup(slug):
    makerspace = make_space(slug)
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
        remaining_weight_grams=Decimal("1000.00"),
    )
    return makerspace, bucket, requester, manager, printer, spool


def _ledger_sum(spool):
    return FilamentAdjustment.objects.filter(filament_spool=spool).aggregate(total=Sum("grams"))["total"] or Decimal("0.00")


def test_print_start_and_complete_append_ledger_rows_matching_spool_decrement():
    makerspace, bucket, requester, manager, printer, spool = _setup("ledger-lifecycle")
    print_request = make_request(bucket, requester)

    workflow.accept(print_request, manager)
    started = workflow.start(
        print_request,
        manager,
        printer_id=printer.id,
        filament_spool_id=spool.id,
        estimated_minutes=60,
        estimated_filament_grams=Decimal("100.00"),
    )
    workflow.complete(started, manager, actual_filament_grams=Decimal("72.50"))

    spool.refresh_from_db()
    rows = list(FilamentAdjustment.objects.filter(filament_spool=spool).order_by("created_at", "id"))
    assert [row.kind for row in rows] == [
        FilamentAdjustment.Kind.RESERVE,
        FilamentAdjustment.Kind.RECONCILE,
    ]
    assert [row.grams for row in rows] == [Decimal("-100.00"), Decimal("27.50")]
    assert _ledger_sum(spool) == Decimal("-72.50")
    assert spool.initial_weight_grams - spool.remaining_weight_grams == Decimal("72.50")
    assert all(row.print_request_id == started.id for row in rows)


def test_manual_print_log_appends_manual_ledger_row():
    makerspace, _, _, manager, printer, spool = _setup("ledger-manual")

    log = services_manual_logs.log_manual_print(
        manager,
        makerspace,
        printer,
        spool,
        Decimal("18.25"),
        "Walk-up print",
        "",
    )

    spool.refresh_from_db()
    adjustment = FilamentAdjustment.objects.get(filament_spool=spool)
    assert adjustment.kind == FilamentAdjustment.Kind.MANUAL
    assert adjustment.grams == Decimal("-18.25")
    assert adjustment.manual_log_id == log.id
    assert spool.remaining_weight_grams == Decimal("981.75")


def test_staff_correction_appends_adjustment_without_rewriting_prior_rows():
    makerspace, _, _, manager, printer, spool = _setup("ledger-correction")
    services_manual_logs.log_manual_print(
        manager, makerspace, printer, spool, Decimal("25.00"), "Manual", ""
    )
    prior = list(FilamentAdjustment.objects.filter(filament_spool=spool).values("id", "kind", "grams"))

    response = authenticated_client(manager).post(
        spool_adjustment_url(spool),
        {"kind": "correction", "grams": "10.00", "reason": "Scale was off"},
        format="json",
    )

    assert response.status_code == 200
    spool.refresh_from_db()
    assert spool.remaining_weight_grams == Decimal("985.00")
    assert list(FilamentAdjustment.objects.filter(id__in=[row["id"] for row in prior]).values("id", "kind", "grams")) == prior
    correction = FilamentAdjustment.objects.latest("id")
    assert correction.kind == FilamentAdjustment.Kind.CORRECTION
    assert correction.grams == Decimal("10.00")
    assert correction.reason == "Scale was off"
    assert AuditLog.objects.filter(action="print.spool_adjusted", target_id=str(spool.id)).exists()


def test_reports_sum_ledger_rows_for_post_ledger_spools():
    makerspace, _, _, manager, _, spool = _setup("ledger-report")
    spool.remaining_weight_grams = Decimal("800.00")
    spool.save(update_fields=["remaining_weight_grams", "updated_at"])
    FilamentAdjustment.objects.create(
        filament_spool=spool,
        makerspace=makerspace,
        kind=FilamentAdjustment.Kind.MANUAL,
        grams=Decimal("-45.50"),
        reason="Post-ledger usage",
        created_by=manager,
    )

    response = authenticated_client(manager).get(makerspace_report_url(makerspace))

    assert response.status_code == 200
    assert response.data["filament_used"][0]["grams_used"] == 45.5
    assert response.data["total_grams_used"] == 45.5
    assert response.data["filament_by_brand"] == [
        {"brand": "Generic", "grams_used": 45.5, "spools": 1}
    ]


def test_reports_fall_back_to_state_math_for_pre_ledger_spools():
    makerspace, _, _, manager, _, spool = _setup("ledger-fallback")
    spool.remaining_weight_grams = Decimal("875.25")
    spool.save(update_fields=["remaining_weight_grams", "updated_at"])

    response = authenticated_client(manager).get(makerspace_report_url(makerspace))

    assert response.status_code == 200
    assert FilamentAdjustment.objects.filter(filament_spool=spool).count() == 0
    assert response.data["filament_used"][0]["grams_used"] == 124.75
    assert response.data["total_grams_used"] == 124.75
