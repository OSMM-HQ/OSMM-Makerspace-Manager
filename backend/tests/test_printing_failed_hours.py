from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.printing import workflow
from apps.printing.models import PrintPrinter, PrintRequest
from apps.printing.reports import build_printing_report
from tests.test_printing import (
    make_bucket,
    make_print_manager,
    make_request,
    make_space,
    make_user,
)

pytestmark = pytest.mark.django_db


def test_fail_persists_percent_and_failed_at():
    makerspace = make_space("failhours-persist")
    bucket = make_bucket(makerspace)
    requester = make_user("failhours-persist-req", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("failhours-persist-mgr", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="FailRig")
    print_request = make_request(bucket, requester, status=PrintRequest.Status.PRINTING)
    print_request.printer = printer
    print_request.estimated_minutes = 120
    print_request.save(update_fields=["printer", "estimated_minutes"])

    workflow.fail(print_request, manager, "Layer shift", percent_complete=50)

    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.FAILED
    assert print_request.fail_percent_complete == 50
    assert print_request.failed_at is not None


def test_printer_hours_include_failed_partial():
    makerspace = make_space("failhours-report")
    bucket = make_bucket(makerspace)
    requester = make_user("failhours-report-req", access_status=User.AccessStatus.ACTIVE)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="PartialRig")
    PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Half print",
        quantity=1,
        status=PrintRequest.Status.FAILED,
        printer=printer,
        estimated_minutes=120,
        fail_percent_complete=50,
        failed_at=timezone.now(),
    )

    report = build_printing_report(makerspace.id)
    rows = {row["printer_id"]: row for row in report["printer_hours"]}

    # 120 min * 50% = 60 min = 1.0h
    assert printer.id in rows
    assert rows[printer.id]["hours"] == 1.0
    assert rows[printer.id]["completed_requests"] == 0
