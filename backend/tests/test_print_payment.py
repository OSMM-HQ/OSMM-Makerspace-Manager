from decimal import Decimal

import pytest
from django.core import mail
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.printing.emails import send_print_email
from apps.printing.models import FilamentSpool, PrintPrinter, PrintRequest
from apps.printing import workflow
from tests.test_printing import (
    action_url,
    authenticated_client,
    make_bucket,
    make_member,
    make_print_manager,
    make_request,
    make_space,
    make_user,
    makerspace_report_url,
    managed_detail_url,
    request_detail_url,
    request_list_url,
)

pytestmark = pytest.mark.django_db


PRIVATE_PAYMENT_KEYS = {
    "price",
    "payment_status",
    "paid_at",
    "collected_at",
    "collected_by",
}


def public_status_url(print_request):
    return reverse(
        "printing:public-request-status",
        kwargs={"public_token": str(print_request.public_token)},
    )


def public_status_by_email_url(makerspace):
    return reverse(
        "printing:public-request-status-by-email",
        kwargs={"makerspace_slug": makerspace.slug},
    )


def _results(response):
    data = response.data
    if isinstance(data, dict) and "results" in data:
        data = data["results"]
    return data


def _item_for(response, print_request):
    return next(item for item in _results(response) if item["id"] == print_request.id)


def _assert_no_keys(data, forbidden):
    if isinstance(data, dict):
        assert not (set(data) & forbidden)
        for value in data.values():
            _assert_no_keys(value, forbidden)
    elif isinstance(data, list):
        for item in data:
            _assert_no_keys(item, forbidden)


def _complete_with_api(client, print_request, *, price=None):
    accept_payload = {} if price is None else {"price": price}
    response = client.post(
        action_url(print_request, "accept"),
        accept_payload,
        format="json",
    )
    assert response.status_code == 200

    response = client.post(action_url(print_request, "start"), format="json")
    assert response.status_code == 200

    response = client.post(action_url(print_request, "complete"), format="json")
    assert response.status_code == 200
    print_request.refresh_from_db()
    return print_request


def _make_printer_and_spool(makerspace):
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        color="black",
        initial_weight_grams=Decimal("1000.00"),
        remaining_weight_grams=Decimal("1000.00"),
    )
    return printer, spool


def test_accept_with_price_sets_price_and_pending_after_complete():
    makerspace = make_space("payment-priced")
    bucket = make_bucket(makerspace)
    requester = make_user("payment-priced-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("payment-priced-manager", makerspace)
    print_request = make_request(bucket, requester)
    client = authenticated_client(manager)

    _complete_with_api(client, print_request, price="10.00")

    assert print_request.price == Decimal("10.00")
    assert print_request.payment_status == PrintRequest.PaymentStatus.PENDING

    response = client.get(managed_detail_url(print_request))
    assert response.status_code == 200
    assert response.data["price"] == "10.00"
    assert response.data["payment_status"] == PrintRequest.PaymentStatus.PENDING


def test_free_request_payment_status_none():
    makerspace = make_space("payment-free")
    bucket = make_bucket(makerspace)
    requester = make_user("payment-free-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("payment-free-manager", makerspace)
    print_request = make_request(bucket, requester)

    _complete_with_api(authenticated_client(manager), print_request)

    assert print_request.price == Decimal("0.00")
    assert print_request.payment_status == PrintRequest.PaymentStatus.NONE


def test_collect_paid_marks_paid_and_collected():
    makerspace = make_space("payment-collect-paid")
    bucket = make_bucket(makerspace)
    requester = make_user("payment-collect-paid-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("payment-collect-paid-manager", makerspace)
    print_request = make_request(bucket, requester)
    client = authenticated_client(manager)
    _complete_with_api(client, print_request, price="10.00")

    response = client.post(action_url(print_request, "collect"), format="json")

    assert response.status_code == 200
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.COLLECTED
    assert print_request.payment_status == PrintRequest.PaymentStatus.PAID
    assert print_request.paid_at is not None
    assert print_request.collected_at is not None
    assert print_request.collected_by == manager
    assert AuditLog.objects.filter(
        action="print.collected",
        target_id=str(print_request.id),
    ).exists()


def test_collect_free_marks_collected_without_payment():
    makerspace = make_space("payment-collect-free")
    bucket = make_bucket(makerspace)
    requester = make_user("payment-collect-free-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("payment-collect-free-manager", makerspace)
    print_request = make_request(bucket, requester)
    client = authenticated_client(manager)
    _complete_with_api(client, print_request)

    response = client.post(action_url(print_request, "collect"), format="json")

    assert response.status_code == 200
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.COLLECTED
    assert print_request.collected_at is not None
    assert print_request.collected_by == manager
    assert print_request.payment_status == PrintRequest.PaymentStatus.NONE
    assert print_request.paid_at is None


@pytest.mark.parametrize(
    "initial_status",
    [
        PrintRequest.Status.PENDING,
        PrintRequest.Status.ACCEPTED,
        PrintRequest.Status.PRINTING,
    ],
)
def test_collect_requires_completed(initial_status):
    makerspace = make_space(f"payment-collect-requires-{initial_status}")
    bucket = make_bucket(makerspace)
    requester = make_user(
        f"payment-collect-requires-requester-{initial_status}",
        access_status=User.AccessStatus.ACTIVE,
    )
    manager = make_print_manager(f"payment-collect-requires-manager-{initial_status}", makerspace)
    print_request = make_request(bucket, requester, status=initial_status)

    response = authenticated_client(manager).post(
        action_url(print_request, "collect"),
        format="json",
    )

    assert response.status_code == 409
    print_request.refresh_from_db()
    assert print_request.status == initial_status
    assert print_request.collected_at is None


def test_collect_permission():
    makerspace = make_space("payment-collect-permission")
    bucket = make_bucket(makerspace)
    requester = make_user("payment-collect-permission-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("payment-collect-permission-manager", makerspace)
    print_request = make_request(bucket, requester)
    _complete_with_api(authenticated_client(manager), print_request, price="10.00")

    response = authenticated_client(requester).post(
        action_url(print_request, "collect"),
        format="json",
    )

    assert response.status_code in (403, 404)
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.COMPLETED
    assert print_request.payment_status == PrintRequest.PaymentStatus.PENDING


def test_price_never_leaks_to_requester():
    makerspace = make_space("payment-requester-private")
    bucket = make_bucket(makerspace)
    requester = make_user("payment-requester-private-user", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("payment-requester-private-manager", makerspace)
    print_request = make_request(bucket, requester)
    _complete_with_api(authenticated_client(manager), print_request, price="10.00")
    client = authenticated_client(requester)

    response = client.get(request_list_url())
    assert response.status_code == 200
    _assert_no_keys(_item_for(response, print_request), PRIVATE_PAYMENT_KEYS)

    response = client.get(request_detail_url(print_request))
    assert response.status_code == 200
    _assert_no_keys(response.data, PRIVATE_PAYMENT_KEYS)


def test_price_never_leaks_public():
    makerspace = make_space("payment-public-private")
    bucket = make_bucket(makerspace)
    requester = make_user("payment-public-private-user", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("payment-public-private-manager", makerspace)
    print_request = make_request(bucket, requester, title="Bracket")
    print_request.contact_email = "buyer@example.com"
    print_request.save(update_fields=["contact_email", "updated_at"])
    _complete_with_api(authenticated_client(manager), print_request, price="10.00")
    client = APIClient()
    forbidden = PRIVATE_PAYMENT_KEYS | {"amount"}

    response = client.get(public_status_url(print_request))
    assert response.status_code == 200
    _assert_no_keys(response.data, forbidden)

    response = client.post(
        public_status_by_email_url(makerspace),
        {"email": "BUYER@example.com"},
        format="json",
    )
    assert response.status_code == 200
    _assert_no_keys(response.data, forbidden)


@pytest.mark.parametrize("event", ["accepted", "completed"])
def test_price_never_leaks_in_email(settings, event, django_capture_on_commit_callbacks):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox = []
    makerspace = make_space(f"mail-cash-{event}")
    bucket = make_bucket(makerspace)
    requester = make_user(
        f"mail-cash-requester-{event}",
        access_status=User.AccessStatus.ACTIVE,
    )
    print_request = make_request(bucket, requester, title="Bracket")
    workflow.accept(print_request, requester, price=Decimal("10.00"))
    if event == "completed":
        workflow.start(print_request, requester)
        workflow.complete(print_request, requester)
    print_request.refresh_from_db()

    # Email delivery is async (dispatch_email -> on_commit -> Celery task); fire the
    # commit hooks so the eager task actually sends.
    with django_capture_on_commit_callbacks(execute=True):
        send_print_email(event, print_request)

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    html, mimetype = message.alternatives[0]
    assert mimetype == "text/html"
    rendered = "\n".join([message.subject, message.body, html]).lower()
    assert "10.00" not in rendered
    assert "price" not in rendered
    assert "payment" not in rendered
    assert "paid" not in rendered


def test_report_payments_totals():
    makerspace = make_space("payment-report")
    bucket = make_bucket(makerspace)
    requester = make_user("payment-report-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("payment-report-manager", makerspace)
    printer, spool = _make_printer_and_spool(makerspace)

    paid = make_request(bucket, requester, title="Paid")
    workflow.accept(paid, manager, price=Decimal("10.00"))
    workflow.start(
        paid,
        manager,
        printer_id=printer.id,
        filament_spool_id=spool.id,
        estimated_minutes=60,
        estimated_filament_grams=Decimal("0.00"),
    )
    workflow.complete(paid, manager)
    workflow.mark_collected(paid, manager)

    pending = make_request(bucket, requester, title="Pending")
    workflow.accept(pending, manager, price=Decimal("5.50"))
    workflow.start(
        pending,
        manager,
        printer_id=printer.id,
        filament_spool_id=spool.id,
        estimated_minutes=30,
        estimated_filament_grams=Decimal("0.00"),
    )
    workflow.complete(pending, manager)

    drifted_paid = make_request(
        bucket,
        requester,
        title="Drifted paid",
        status=PrintRequest.Status.ACCEPTED,
    )
    drifted_paid.price = Decimal("99.00")
    drifted_paid.payment_status = PrintRequest.PaymentStatus.PAID
    drifted_paid.save(update_fields=["price", "payment_status", "updated_at"])
    drifted_pending = make_request(
        bucket,
        requester,
        title="Drifted pending",
        status=PrintRequest.Status.PRINTING,
    )
    drifted_pending.price = Decimal("42.00")
    drifted_pending.payment_status = PrintRequest.PaymentStatus.PENDING
    drifted_pending.save(update_fields=["price", "payment_status", "updated_at"])

    response = authenticated_client(manager).get(makerspace_report_url(makerspace))

    assert response.status_code == 200
    assert response.data["payments"] == {
        "paid_amount": "10.00",
        "paid_count": 1,
        "outstanding_amount": "5.50",
        "outstanding_count": 1,
    }
    assert response.data["totals"]["collected"] == 1
    assert response.data["printer_hours"] == [
        {
            "printer_id": printer.id,
            "printer_name": "Prusa MK4",
            "image_url": None,
            "completed_requests": 2,
            "hours": 1.5,
        }
    ]


def test_report_per_makerspace_hardhide_403():
    hidden_space = make_space("payment-report-hidden")
    hidden_space.superadmin_access_enabled = False
    hidden_space.save(update_fields=["superadmin_access_enabled"])
    manager = make_member("payment-report-hidden-manager", hidden_space)
    superadmin = make_user(
        "payment-report-hidden-super",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )

    # Hard hide: a global superadmin is FORBIDDEN (403) from a disabled space's
    # report. Existence isn't secret (the makerspace still shows as a slim row in
    # the makerspace list), so 403 "forbidden" is the honest status, not a 404.
    response = authenticated_client(superadmin).get(makerspace_report_url(hidden_space))
    assert response.status_code == 403

    response = authenticated_client(manager).get(makerspace_report_url(hidden_space))
    assert response.status_code == 200


def test_reprint_carries_price():
    makerspace = make_space("payment-reprint")
    bucket = make_bucket(makerspace)
    requester = make_user("payment-reprint-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("payment-reprint-manager", makerspace)
    failed = make_request(bucket, requester, title="Failed bracket")
    workflow.accept(failed, manager, price=Decimal("10.00"))
    workflow.start(failed, manager)
    workflow.fail(failed, manager, "warped")
    failed.refresh_from_db()

    response = authenticated_client(manager).post(
        action_url(failed, "reprint"),
        format="json",
    )

    assert response.status_code == 201
    clone = PrintRequest.objects.get(pk=response.data["id"])
    assert clone.id != failed.id
    assert clone.reprint_of_id == failed.id
    assert clone.price == Decimal("10.00")
    assert clone.payment_status == PrintRequest.PaymentStatus.NONE
    assert response.data["price"] == "10.00"
    assert response.data["payment_status"] == PrintRequest.PaymentStatus.NONE
