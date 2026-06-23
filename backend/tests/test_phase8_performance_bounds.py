from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem
from apps.inventory.models import InventoryProduct
from apps.printing.models import PrintBucket, PrintRequest
from apps.printing.queue_position import queue_counts_for
from apps.procurement.models import ToBuyItem
from tests.return_helpers import authenticated_client, make_member, make_product, make_space, make_user

pytestmark = pytest.mark.django_db


def test_ledger_pages_results_without_changing_total_count():
    space = make_space("phase8-ledger")
    manager = make_member("phase8-ledger-manager", space)
    product = make_product(space, name="Shared Drill")
    created = [_issued_request(space, product, f"phase8-ledger-{index}") for index in range(3)]

    response = authenticated_client(manager).get(
        f"/api/v1/admin/makerspace/{space.id}/ledger?page=2&page_size=2"
    )

    assert response.status_code == 200
    assert response.data["count"] == 3
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["reference_id"] in {request.id for request in created}


def test_report_preview_limit_keeps_rows_enveloped_and_export_full():
    space = make_space("phase8-report")
    manager = make_member("phase8-report-manager", space)
    for index in range(3):
        make_product(space, name=f"Report Product {index}")

    client = authenticated_client(manager)
    preview = client.get(f"/api/v1/admin/makerspace/{space.id}/analytics/recently-added?limit=2")
    exported = client.get(f"/api/v1/admin/makerspace/{space.id}/reports/recently-added/export")

    assert preview.status_code == 200
    assert list(preview.data) == ["rows"]
    assert len(preview.data["rows"]) == 3
    assert exported.status_code == 200
    assert exported.content.decode().count("Report Product") == 3


def test_procurement_list_limit_bounds_raw_list_without_limiting_export():
    space = make_space("phase8-procurement")
    manager = make_member("phase8-proc-manager", space)
    for index in range(3):
        ToBuyItem.objects.create(makerspace=space, kind=ToBuyItem.Kind.HARDWARE, name=f"Buy {index}")

    client = authenticated_client(manager)
    listed = client.get(f"/api/v1/procurement/makerspace/{space.id}/to-buy?limit=1")
    exported = client.get(f"/api/v1/procurement/makerspace/{space.id}/to-buy/export")

    assert listed.status_code == 200
    assert isinstance(listed.data, list)
    assert len(listed.data) == 1
    assert exported.status_code == 200
    assert exported.content.decode().count("Buy ") == 3


def test_queue_position_uses_same_rank_rules_for_target_requests():
    space = make_space("phase8-queue")
    bucket = PrintBucket.objects.create(makerspace=space, name="PLA")
    requester = make_user("phase8-print-user", access_status=User.AccessStatus.ACTIVE)
    first = _print_request(bucket, requester, "First", PrintRequest.Status.ACCEPTED, minutes_ago=5)
    pending = _print_request(bucket, requester, "Pending", PrintRequest.Status.PENDING, minutes_ago=4)
    second = _print_request(bucket, requester, "Second", PrintRequest.Status.ACCEPTED, minutes_ago=3)
    printing = _print_request(bucket, requester, "Printing", PrintRequest.Status.PRINTING, minutes_ago=2)

    counts = queue_counts_for(space, [second, pending, printing])

    assert counts[second.id] == {"position": 2, "approved_ahead": 1, "awaiting_review_ahead": 0}
    assert counts[pending.id] == {"position": 3, "approved_ahead": 2, "awaiting_review_ahead": 0}
    assert printing.id not in counts
    assert first.id not in counts


def test_phase8_indexes_are_declared_on_hot_models():
    procurement_indexes = {index.name for index in ToBuyItem._meta.indexes}
    print_indexes = {index.name for index in PrintRequest._meta.indexes}

    assert "proc_tobuy_scope_created_idx" in procurement_indexes
    assert "printreq_contact_email_l_idx" in print_indexes


def _issued_request(space, product, username):
    requester = make_user(username, access_status=User.AccessStatus.ACTIVE)
    request = HardwareRequest.objects.create(
        makerspace=space,
        requester=requester,
        requester_username=requester.username,
        status=HardwareRequest.Status.ISSUED,
        issued_at=timezone.now(),
    )
    HardwareRequestItem.objects.create(
        request=request,
        product=product,
        requested_quantity=1,
        accepted_quantity=1,
        issued_quantity=1,
    )
    InventoryProduct.objects.filter(pk=product.pk).update(available_quantity=9, issued_quantity=1)
    return request


def _print_request(bucket, requester, title, status, *, minutes_ago):
    request = PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title=title,
        status=status,
    )
    request.created_at = timezone.now() - timedelta(minutes=minutes_ago)
    request.save(update_fields=["created_at"])
    return request