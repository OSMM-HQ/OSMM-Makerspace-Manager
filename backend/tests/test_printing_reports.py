from datetime import datetime, timezone
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.makerspaces.models import MakerspaceMembership
from apps.printing.models import (
    FilamentSpool,
    ManualPrintLog,
    PrintPrinter,
    PrintRequest,
)
from tests.test_printing import (
    authenticated_client,
    make_bucket,
    make_member,
    make_print_manager,
    make_request,
    make_space,
    make_user,
)

pytestmark = pytest.mark.django_db


def makerspace_report_url(makerspace):
    return reverse(
        "printing:makerspace-report",
        kwargs={"makerspace_id": makerspace.id},
    )


def admin_report_url():
    return reverse("printing:admin-report")


def completed_at(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def make_completed_request(
    bucket,
    requester,
    printer,
    spool,
    title,
    minutes,
    grams,
    completed,
):
    return PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title=title,
        quantity=1,
        status=PrintRequest.Status.COMPLETED,
        printer=printer,
        filament_spool=spool,
        estimated_minutes=minutes,
        estimated_filament_grams=Decimal(grams),
        completed_at=completed,
    )


def test_makerspace_printing_report_aggregates_totals_hours_filament_and_periods():
    makerspace = make_space("reports-main")
    other_space = make_space("reports-other")
    bucket = make_bucket(makerspace)
    other_bucket = make_bucket(other_space)
    requester = make_user("reports-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("reports-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        color="black",
        initial_weight_grams=1000,
        remaining_weight_grams=650,
    )
    other_printer = PrintPrinter.objects.create(makerspace=other_space, name="Other")
    other_spool = FilamentSpool.objects.create(
        makerspace=other_space,
        printer=other_printer,
        material="PETG",
        color="orange",
        initial_weight_grams=1000,
        remaining_weight_grams=900,
    )

    make_completed_request(
        bucket,
        requester,
        printer,
        spool,
        "Bracket",
        90,
        "120.00",
        completed_at(2026, 5, 1, 10, 15),
    )
    make_completed_request(
        bucket,
        requester,
        printer,
        spool,
        "Clip",
        30,
        "80.50",
        completed_at(2026, 5, 1, 10, 45),
    )
    make_completed_request(
        bucket,
        requester,
        printer,
        spool,
        "Case",
        60,
        "40.00",
        completed_at(2026, 5, 2, 11),
    )
    make_request(bucket, requester, title="Failed", status=PrintRequest.Status.FAILED)
    make_request(bucket, requester, title="Rejected", status=PrintRequest.Status.REJECTED)
    make_request(bucket, requester, title="Pending", status=PrintRequest.Status.PENDING)
    make_request(bucket, requester, title="Printing", status=PrintRequest.Status.PRINTING)
    make_request(bucket, requester, title="Accepted", status=PrintRequest.Status.ACCEPTED)
    make_completed_request(
        other_bucket,
        requester,
        other_printer,
        other_spool,
        "Other space",
        500,
        "500.00",
        completed_at(2026, 5, 1, 10),
    )

    response = authenticated_client(manager).get(makerspace_report_url(makerspace))

    assert response.status_code == 200
    assert response.data["totals"] == {
        "total_requests": 8,
        "completed": 3,
        "collected": 0,
        "failed": 1,
        "rejected": 1,
        "pending": 1,
        "printing": 1,
        "accepted": 1,
    }
    assert response.data["printer_hours"] == [
        {
            "printer_id": printer.id,
            "printer_name": "Prusa MK4",
            "image_url": None,
            "completed_requests": 3,
            "hours": 3.0,
        }
    ]
    assert response.data["filament_used"] == [
        {
            "spool_id": spool.id,
            "material": "PLA",
            "color": "black",
            "grams_used": 350.0,
            "remaining_grams": 650.0,
        }
    ]
    assert response.data["total_grams_used"] == 350.0
    assert response.data["filament_estimated_by_period"]["by_month"] == [
        {"period": "2026-05", "grams": 240.5}
    ]
    assert response.data["filament_estimated_by_period"]["by_day"] == [
        {"period": "2026-05-01", "grams": 200.5},
        {"period": "2026-05-02", "grams": 40.0},
    ]
    assert response.data["filament_estimated_by_period"]["by_hour"] == [
        {"period": "2026-05-01 10:00", "grams": 200.5},
        {"period": "2026-05-02 11:00", "grams": 40.0},
    ]
    # Top requesters: who submits the most print jobs, ranked high-to-low.
    requesters = response.data["top_requesters"]
    assert requesters, "top_requesters should not be empty"
    assert {"requester", "requests", "items"} <= set(requesters[0].keys())
    counts = [row["requests"] for row in requesters]
    assert counts == sorted(counts, reverse=True)


def test_printing_report_accepts_date_range_filters():
    makerspace = make_space("reports-print-date-range")
    bucket = make_bucket(makerspace)
    requester = make_user("reports-print-date-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("reports-print-date-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Date Printer")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        color="black",
        initial_weight_grams=1000,
        remaining_weight_grams=800,
    )
    make_completed_request(
        bucket, requester, printer, spool, "In range", 30, "50.00", completed_at(2026, 5, 10, 9)
    )
    make_completed_request(
        bucket, requester, printer, spool, "Out of range", 60, "90.00", completed_at(2026, 6, 10, 9)
    )

    response = authenticated_client(manager).get(
        f"{makerspace_report_url(makerspace)}?start=2026-05-01&end=2026-05-31"
    )

    assert response.status_code == 200
    assert response.data["printer_hours"][0]["completed_requests"] == 1
    assert response.data["printer_hours"][0]["hours"] == 0.5
    assert response.data["filament_estimated_by_period"]["by_month"] == [
        {"period": "2026-05", "grams": 50.0}
    ]


def test_printing_report_keeps_estimate_based_request_grams_separate_from_spool_delta():
    makerspace = make_space("reports-estimate-axis")
    bucket = make_bucket(makerspace)
    requester = make_user("reports-estimate-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("reports-estimate-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Estimate rig")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        color="blue",
        initial_weight_grams=1000,
        remaining_weight_grams=820,
    )
    print_request = make_completed_request(
        bucket,
        requester,
        printer,
        spool,
        "Estimated print",
        45,
        "120.00",
        completed_at(2026, 5, 3, 12),
    )
    # Completion reconciles request-side usage from estimated_filament_grams.
    print_request.filament_grams_used = Decimal("120.00")
    print_request.save(update_fields=["filament_grams_used"])
    ManualPrintLog.objects.create(
        makerspace=makerspace,
        printer=printer,
        filament_spool=spool,
        grams_used=Decimal("30.00"),
        title="Manual calibration",
        note="",
        logged_by=manager,
    )

    response = authenticated_client(manager).get(makerspace_report_url(makerspace))

    assert response.status_code == 200
    assert response.data["printer_outcomes"] == [
        {
            "printer_id": printer.id,
            "printer_name": "Estimate rig",
            "image_url": None,
            "completed": 1,
            "failed": 0,
            "grams_used": 150.0,
            "manual_logs": 1,
        }
    ]
    assert response.data["filament_estimated_by_period"]["by_day"] == [
        {"period": "2026-05-03", "grams": 120.0}
    ]
    assert response.data["filament_used"] == [
        {
            "spool_id": spool.id,
            "material": "PLA",
            "color": "blue",
            "grams_used": 180.0,
            "remaining_grams": 820.0,
        }
    ]
    assert response.data["total_grams_used"] == 180.0


def test_printing_report_filament_by_brand_ranks_usage_and_falls_back_to_unbranded():
    makerspace = make_space("reports-brand")
    manager = make_print_manager("reports-brand-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Brand rig")

    def spool(brand, initial, remaining):
        return FilamentSpool.objects.create(
            makerspace=makerspace,
            printer=printer,
            material="PLA",
            color="black",
            brand=brand,
            initial_weight_grams=initial,
            remaining_weight_grams=remaining,
        )

    # Polymaker: 400 + 200 = 600g across 2 spools (top). Blank brand -> "Unbranded"
    # at 200g. eSUN: 100g (lowest). Result is ranked grams-used high-to-low.
    spool("Polymaker", 1000, 600)
    spool("Polymaker", 500, 300)
    spool("eSUN", 1000, 900)
    spool("", 1000, 800)

    response = authenticated_client(manager).get(makerspace_report_url(makerspace))

    assert response.status_code == 200
    assert response.data["filament_by_brand"] == [
        {"brand": "Polymaker", "grams_used": 600.0, "spools": 2},
        {"brand": "Unbranded", "grams_used": 200.0, "spools": 1},
        {"brand": "eSUN", "grams_used": 100.0, "spools": 1},
    ]


def test_admin_makerspaces_list_includes_a_print_managers_makerspace():
    # Regression: the staff switcher lists makerspaces via VIEW_INVENTORY OR
    # MANAGE_PRINTING. A pure print manager (no VIEW_INVENTORY) must still see
    # their makerspace, otherwise the React console strands them on "No makerspace".
    space = make_space("reports-switcher")
    other = make_space("reports-switcher-other")
    manager = make_print_manager("reports-switcher-manager", space)

    response = authenticated_client(manager).get("/api/v1/admin/makerspaces")

    assert response.status_code == 200
    rows = {row["id"]: row for row in response.data}
    assert space.id in rows
    assert other.id not in rows
    # Slim switcher serializer: a print manager must NOT receive the full config
    # (public_api_key, CORS origins, SMTP host/username) the settings views gate
    # behind MANAGE_MAKERSPACE.
    row = rows[space.id]
    assert set(row) == {"id", "name", "public_code", "slug", "telegram_group_chat_id"}
    for leaked in ("public_api_key", "cors_allowed_origins", "smtp_host", "smtp_username", "enabled_modules"):
        assert leaked not in row


def test_admin_makerspaces_list_is_slim_only_for_print_only_rows_of_mixed_role_user():
    # Mixed role: VIEW_INVENTORY in space_a, MANAGE_PRINTING-only in space_b. The
    # list must show space_a in full but space_b slim — a single serializer choice
    # for the whole list would leak space_b's config (public_api_key/SMTP/CORS).
    space_a = make_space("reports-mixed-a")
    space_b = make_space("reports-mixed-b")
    user = make_member(
        "reports-mixed-user",
        space_a,
        membership_role=MakerspaceMembership.Role.SPACE_MANAGER,
        role=User.Role.SPACE_MANAGER,
    )
    MakerspaceMembership.objects.create(
        user=user,
        makerspace=space_b,
        role=MakerspaceMembership.Role.PRINT_MANAGER,
    )

    response = authenticated_client(user).get("/api/v1/admin/makerspaces")

    assert response.status_code == 200
    rows = {row["id"]: row for row in response.data}
    assert set(rows) == {space_a.id, space_b.id}
    # Full row for the VIEW_INVENTORY makerspace.
    assert "public_api_key" in rows[space_a.id]
    # Slim row for the print-only makerspace — no leaked config.
    assert set(rows[space_b.id]) == {"id", "name", "public_code", "slug", "telegram_group_chat_id"}
    assert "public_api_key" not in rows[space_b.id]


def test_makerspace_printing_report_requires_manage_printing_scope():
    own_space = make_space("reports-scope-own")
    other_space = make_space("reports-scope-other")
    guest = make_member(
        "reports-scope-guest",
        own_space,
        membership_role=MakerspaceMembership.Role.GUEST_ADMIN,
        role=User.Role.GUEST_ADMIN,
    )
    manager = make_print_manager("reports-scope-manager", own_space)

    response = authenticated_client(guest).get(makerspace_report_url(own_space))
    assert response.status_code in (403, 404)

    response = authenticated_client(manager).get(makerspace_report_url(other_space))
    assert response.status_code in (403, 404)


def test_admin_printing_report_is_superadmin_only_and_includes_makerspaces():
    space_a = make_space("reports-admin-a")
    space_b = make_space("reports-admin-b")
    bucket_a = make_bucket(space_a)
    bucket_b = make_bucket(space_b)
    requester = make_user("reports-admin-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("reports-admin-manager", space_a)
    superadmin = make_user(
        "reports-admin-super",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )
    printer_a = PrintPrinter.objects.create(makerspace=space_a, name="A1")
    printer_b = PrintPrinter.objects.create(makerspace=space_b, name="X1")
    spool_a = FilamentSpool.objects.create(
        makerspace=space_a,
        printer=printer_a,
        material="PLA",
        color="black",
        initial_weight_grams=1000,
        remaining_weight_grams=900,
    )
    spool_b = FilamentSpool.objects.create(
        makerspace=space_b,
        printer=printer_b,
        material="ABS",
        color="white",
        initial_weight_grams=750,
        remaining_weight_grams=500,
    )
    make_completed_request(
        bucket_a,
        requester,
        printer_a,
        spool_a,
        "A print",
        60,
        "50.00",
        completed_at(2026, 6, 1, 9),
    )
    make_completed_request(
        bucket_b,
        requester,
        printer_b,
        spool_b,
        "B print",
        120,
        "75.00",
        completed_at(2026, 6, 2, 9),
    )

    response = authenticated_client(manager).get(admin_report_url())
    assert response.status_code == 403

    response = authenticated_client(superadmin).get(admin_report_url())

    assert response.status_code == 200
    assert response.data["totals"]["total_requests"] == 2
    assert response.data["total_grams_used"] == 350.0
    assert {row["makerspace_id"] for row in response.data["printer_hours"]} == {
        space_a.id,
        space_b.id,
    }
    assert {row["makerspace_id"] for row in response.data["filament_used"]} == {
        space_a.id,
        space_b.id,
    }


def test_printing_report_top_requesters_ranked_by_grams_printed():
    # The leaderboard ranks by total estimated grams printed, NOT by request count:
    # a user with one big print outranks a user with several tiny prints.
    makerspace = make_space("reports-grams-rank")
    bucket = make_bucket(makerspace)
    manager = make_print_manager("reports-grams-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="G1")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        color="black",
        initial_weight_grams=5000,
        remaining_weight_grams=5000,
    )
    heavy = make_user("grams-heavy", access_status=User.AccessStatus.ACTIVE)
    light = make_user("grams-light", access_status=User.AccessStatus.ACTIVE)
    for index in range(3):
        make_completed_request(
            bucket, light, printer, spool, f"L{index}", 10, "10.00", completed_at(2026, 5, 1, 10)
        )
    make_completed_request(
        bucket, heavy, printer, spool, "H", 100, "500.00", completed_at(2026, 5, 1, 11)
    )

    response = authenticated_client(manager).get(makerspace_report_url(makerspace))

    assert response.status_code == 200
    rows = response.data["top_requesters"]
    # Heavy printer (500g, 1 job) outranks the light one (30g across 3 jobs).
    assert rows[0]["requester"] == "grams-heavy"
    assert rows[0]["grams"] == 500.0
    assert rows[1]["requester"] == "grams-light"
    assert rows[1]["grams"] == 30.0
    assert rows[1]["requests"] == 3
    grams = [row["grams"] for row in rows]
    assert grams == sorted(grams, reverse=True)


def test_printing_report_top_requesters_never_leak_checkin_hash():
    # A public/self-checkout shadow requester carries the privacy hash username
    # checkin_<sha256>. The report's Top requesters must show the readable Check-In
    # identifier (external_checkin_user_id), never the raw hash.
    makerspace = make_space("reports-hash")
    bucket = make_bucket(makerspace)
    manager = make_print_manager("reports-hash-manager", makerspace)
    hashed = "checkin_" + ("b" * 64)
    requester = make_user(
        hashed,
        access_status=User.AccessStatus.ACTIVE,
        external_checkin_user_id="printer-walkin@x.com",
    )
    make_request(bucket, requester, title="Hash job")

    response = authenticated_client(manager).get(makerspace_report_url(makerspace))

    assert response.status_code == 200
    requesters = response.data["top_requesters"]
    assert requesters, "top_requesters should not be empty"
    labels = [row["requester"] for row in requesters]
    assert all(not label.startswith("checkin_") for label in labels)
    assert "printer-walkin@x.com" in labels
