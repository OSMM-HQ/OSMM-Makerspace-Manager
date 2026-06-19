from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import User
from apps.boxes.models import Box, QrCode
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem, PublicToolLoan
from apps.inventory.models import InventoryProduct
from apps.printing.models import FilamentSpool, PrintPrinter, PrintRequest
from tests.return_helpers import authenticated_client
from tests.test_admin_direct_loans import make_admin as make_direct_admin
from tests.test_admin_direct_loans import make_product as make_direct_product
from tests.test_admin_direct_loans import make_space as make_direct_space
from tests.test_printing import make_bucket, make_print_manager, make_space, make_user

pytestmark = pytest.mark.django_db


def _count_queries(django_assert_num_queries, count, func):
    with django_assert_num_queries(count):
        response = func()
    assert response.status_code == 200
    return response


def _capture_query_count(func):
    with CaptureQueriesContext(connection) as captured:
        response = func()
    assert response.status_code == 200
    return len(captured)


def _printer_with_queue(makerspace, bucket, requester, index):
    printer = PrintPrinter.objects.create(makerspace=makerspace, name=f"Printer {index}")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        color=f"Color {index}",
        initial_weight_grams=Decimal("1000.00"),
        remaining_weight_grams=Decimal("900.00"),
    )
    PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title=f"Queued {index}",
        status=PrintRequest.Status.ACCEPTED,
        printer=printer,
        filament_spool=spool,
        estimated_minutes=30,
        estimated_filament_grams=Decimal("25.00"),
    )
    return printer


def test_managed_printer_list_query_count_does_not_grow_per_printer(
    django_assert_num_queries,
):
    makerspace = make_space("perf-printers")
    bucket = make_bucket(makerspace)
    requester = make_user("perf-printer-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("perf-printer-manager", makerspace)
    client = authenticated_client(manager)
    url = f"/api/v1/printing/manage/printers/?makerspace={makerspace.id}"

    _printer_with_queue(makerspace, bucket, requester, 1)
    one_count = _capture_query_count(lambda: client.get(url))

    _printer_with_queue(makerspace, bucket, requester, 2)
    _count_queries(django_assert_num_queries, one_count, lambda: client.get(url))


def _box_with_active_qr(makerspace, label, actor):
    box = Box.objects.create(makerspace=makerspace, label=label)
    QrCode.objects.create(
        makerspace=makerspace,
        payload=box.code,
        target_type=QrCode.TargetType.BOX,
        target_id=box.id,
        created_by=actor,
    )
    return box


def test_container_list_query_count_does_not_grow_per_box(django_assert_num_queries):
    makerspace = make_direct_space("perf-containers")
    manager = make_direct_admin(makerspace)
    client = authenticated_client(manager)
    url = f"/api/v1/admin/makerspace/{makerspace.id}/containers"

    _box_with_active_qr(makerspace, "Box 1", manager)
    one_count = _capture_query_count(lambda: client.get(url))

    _box_with_active_qr(makerspace, "Box 2", manager)
    _count_queries(django_assert_num_queries, one_count, lambda: client.get(url))


def _admin_direct_loan(makerspace, admin, requester, product, index):
    request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        status=HardwareRequest.Status.ISSUED,
        issued_by=admin,
    )
    HardwareRequestItem.objects.create(
        request=request,
        product=product,
        requested_quantity=1,
        accepted_quantity=1,
        issued_quantity=1,
    )
    return PublicToolLoan.objects.create(
        makerspace=makerspace,
        request=request,
        requester=requester,
        target_type="product",
        target_id=product.id,
        target_label=f"Loan {index}",
        status=PublicToolLoan.Status.CHECKED_OUT,
        source=PublicToolLoan.Source.ADMIN_DIRECT,
    )


def test_direct_loan_list_query_count_does_not_grow_per_loan(
    django_assert_num_queries,
):
    makerspace = make_direct_space("perf-direct-loans")
    admin = make_direct_admin(makerspace)
    requester = make_user("perf-direct-requester", access_status=User.AccessStatus.ACTIVE)
    product = make_direct_product(
        makerspace,
        name="Perf Multimeter",
        total_quantity=2,
        available_quantity=0,
        issued_quantity=2,
    )
    client = authenticated_client(admin)
    url = f"/api/v1/admin/makerspace/{makerspace.id}/direct-loans"

    _admin_direct_loan(makerspace, admin, requester, product, 1)
    one_count = _capture_query_count(lambda: client.get(url))

    _admin_direct_loan(makerspace, admin, requester, product, 2)
    _count_queries(django_assert_num_queries, one_count, lambda: client.get(url))
