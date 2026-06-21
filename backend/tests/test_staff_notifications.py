from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.hardware_requests import notifications as hardware_notifications
from apps.hardware_requests.models import HardwareRequest
from apps.integrations.staff_notifications import staff_emails_for_stream
from apps.makerspaces.models import MakerspaceMembership
from apps.printing import workflow as print_workflow
from apps.printing.models import PrintRequest
from tests.return_helpers import (
    authenticated_client as hardware_authenticated_client,
    make_issued_request,
    make_member,
    make_product,
    make_space,
)
from tests.test_issue import (
    assign_scanned_box,
    issue_payload,
    issue_url,
    make_accepted_request,
    make_box,
    make_issue_evidence,
)
from tests.test_printing import (
    action_url as print_action_url,
    authenticated_client as print_authenticated_client,
    make_bucket,
    make_print_manager,
    make_request as make_print_request,
    request_list_url as print_request_list_url,
)

pytestmark = pytest.mark.django_db


def make_user(username, role=User.Role.REQUESTER, **kw):
    return get_user_model().objects.create_user(
        username=username,
        email=kw.pop("email", f"{username}@e.com"),
        role=role,
        **kw,
    )


def add_membership(user, makerspace, role):
    MakerspaceMembership.objects.create(
        user=user,
        makerspace=makerspace,
        role=role,
    )
    return user


def make_staff_user(username, makerspace, membership_role, **kw):
    user = make_user(
        username,
        role=kw.pop("role", User.Role.REQUESTER),
        access_status=kw.pop("access_status", User.AccessStatus.ACTIVE),
        **kw,
    )
    return add_membership(user, makerspace, membership_role)


def public_hardware_submit_url(makerspace):
    return f"/api/v1/public/{makerspace.slug}/requests"


def accept_url(hardware_request):
    return f"/api/v1/admin/requests/{hardware_request.id}/accept"


def reject_url(hardware_request):
    return f"/api/v1/admin/requests/{hardware_request.id}/reject"


def public_print_submit_url(makerspace):
    return reverse(
        "printing:public-request-submit",
        kwargs={"makerspace_slug": makerspace.slug},
    )


def reset_outbox():
    mail.outbox = []


def recipient_addresses():
    return [address for message in mail.outbox for address in message.to]


def assert_address_sent(address):
    assert address in recipient_addresses()


def assert_address_count(address, count):
    assert recipient_addresses().count(address) == count


def test_staff_emails_for_stream_resolves_roles_without_cross_stream_leak():
    makerspace = make_space("staff-resolver-streams")
    space_manager = make_staff_user(
        "resolver-space-manager",
        makerspace,
        MakerspaceMembership.Role.SPACE_MANAGER,
        email="space@example.com",
    )
    inventory_manager = make_staff_user(
        "resolver-inventory-manager",
        makerspace,
        MakerspaceMembership.Role.INVENTORY_MANAGER,
        email="inventory@example.com",
    )
    print_manager = make_staff_user(
        "resolver-print-manager",
        makerspace,
        MakerspaceMembership.Role.PRINT_MANAGER,
        email="print@example.com",
    )

    assert staff_emails_for_stream(makerspace, "hardware") == [
        space_manager.email,
        inventory_manager.email,
    ]
    assert staff_emails_for_stream(makerspace, "printing") == [
        space_manager.email,
        print_manager.email,
    ]
    assert print_manager.email not in staff_emails_for_stream(makerspace, "hardware")
    assert inventory_manager.email not in staff_emails_for_stream(makerspace, "printing")


@pytest.mark.parametrize(
    ("username", "user_kwargs"),
    [
        ("resolver-inactive", {"is_active": False}),
        ("resolver-restricted", {"access_status": User.AccessStatus.RESTRICTED}),
        ("resolver-suspended", {"access_status": User.AccessStatus.SUSPENDED}),
        ("resolver-empty-email", {"email": ""}),
        ("resolver-superuser", {"is_superuser": True}),
        ("resolver-superadmin-role", {"role": User.Role.SUPERADMIN}),
    ],
)
def test_staff_emails_for_stream_excludes_ineligible_members(username, user_kwargs):
    makerspace = make_space(username)
    valid = make_staff_user(
        f"{username}-valid",
        makerspace,
        MakerspaceMembership.Role.SPACE_MANAGER,
        email=f"{username}-valid@example.com",
    )
    make_staff_user(
        username,
        makerspace,
        MakerspaceMembership.Role.INVENTORY_MANAGER,
        **user_kwargs,
    )

    assert staff_emails_for_stream(makerspace, "hardware") == [valid.email]


def test_staff_emails_for_stream_dedupes_case_variant_emails():
    makerspace = make_space("staff-resolver-dedupe")
    make_staff_user(
        "resolver-dedupe-upper",
        makerspace,
        MakerspaceMembership.Role.SPACE_MANAGER,
        email="Foo@Example.com",
    )
    make_staff_user(
        "resolver-dedupe-lower",
        makerspace,
        MakerspaceMembership.Role.INVENTORY_MANAGER,
        email="foo@example.com",
    )

    recipients = staff_emails_for_stream(makerspace, "hardware")

    assert len(recipients) == 1
    assert recipients[0].lower() == "foo@example.com"


def test_staff_emails_for_stream_returns_empty_when_disabled():
    makerspace = make_space("staff-resolver-disabled")
    makerspace.staff_notifications_enabled = False
    makerspace.save(update_fields=["staff_notifications_enabled"])
    make_staff_user(
        "resolver-disabled-manager",
        makerspace,
        MakerspaceMembership.Role.SPACE_MANAGER,
        email="disabled-manager@example.com",
    )

    assert staff_emails_for_stream(makerspace, "hardware") == []


@override_settings(
    API_CLIENT_AUTH_REQUIRED=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_hardware_submitted_emails_requester_and_staff(
    django_capture_on_commit_callbacks,
):
    reset_outbox()
    makerspace = make_space("staff-hardware-submitted")
    product = make_product(makerspace)
    staff = make_staff_user(
        "staff-hardware-submitted-manager",
        makerspace,
        MakerspaceMembership.Role.INVENTORY_MANAGER,
        email="hardware-submitted-staff@example.com",
    )

    with django_capture_on_commit_callbacks(execute=True):
        response = APIClient().post(
            public_hardware_submit_url(makerspace),
            {
                "identifier": "staff-hardware-submitted",
                "contact_email": "hardware-submitted-requester@example.com",
                "items": [{"product_id": product.id, "quantity": 1}],
            },
            format="json",
        )

    assert response.status_code == 201
    assert_address_sent("hardware-submitted-requester@example.com")
    assert_address_sent(staff.email)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
@pytest.mark.parametrize("event", ["accepted", "rejected"])
def test_hardware_review_events_email_requester_and_staff(
    event,
    django_capture_on_commit_callbacks,
):
    reset_outbox()
    makerspace = make_space(f"staff-hardware-{event}")
    product = make_product(makerspace)
    admin = make_member(f"staff-hardware-{event}-admin", makerspace)
    staff = make_staff_user(
        f"staff-hardware-{event}-manager",
        makerspace,
        MakerspaceMembership.Role.INVENTORY_MANAGER,
        email=f"hardware-{event}-staff@example.com",
    )
    hardware_request = make_accepted_request(
        makerspace,
        product,
        1,
        requester=make_user(
            f"staff-hardware-{event}-requester",
            access_status=User.AccessStatus.ACTIVE,
        ),
    )
    hardware_request.status = HardwareRequest.Status.PENDING_APPROVAL
    hardware_request.requester_contact_email = f"hardware-{event}-requester@example.com"
    hardware_request.save(update_fields=["status", "requester_contact_email", "updated_at"])
    product.available_quantity += 1
    product.reserved_quantity -= 1
    product.save(update_fields=["available_quantity", "reserved_quantity", "updated_at"])

    with django_capture_on_commit_callbacks(execute=True):
        if event == "accepted":
            response = hardware_authenticated_client(admin).post(
                accept_url(hardware_request),
                format="json",
            )
        else:
            response = hardware_authenticated_client(admin).post(
                reject_url(hardware_request),
                {"reason": "Not available today."},
                format="json",
            )

    assert response.status_code == 200
    assert_address_sent(f"hardware-{event}-requester@example.com")
    assert_address_sent(staff.email)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_hardware_issued_emails_requester_and_staff(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    reset_outbox()
    makerspace = make_space("staff-hardware-issued")
    admin = make_member("staff-hardware-issued-admin", makerspace)
    staff = make_staff_user(
        "staff-hardware-issued-manager",
        makerspace,
        MakerspaceMembership.Role.INVENTORY_MANAGER,
        email="hardware-issued-staff@example.com",
    )
    product = make_product(makerspace)
    hardware_request = make_accepted_request(makerspace, product, 1)
    hardware_request.requester_contact_email = "hardware-issued-requester@example.com"
    hardware_request.save(update_fields=["requester_contact_email", "updated_at"])
    box = make_box(makerspace)
    assign_scanned_box(hardware_request, box, admin)
    evidence = make_issue_evidence(makerspace, admin)
    monkeypatch.setattr("apps.evidence.storage.object_exists", Mock(return_value=True))

    with django_capture_on_commit_callbacks(execute=True):
        response = hardware_authenticated_client(admin).post(
            issue_url(hardware_request),
            issue_payload(evidence),
            format="json",
        )

    assert response.status_code == 200
    assert_address_sent("hardware-issued-requester@example.com")
    assert_address_sent(staff.email)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
@pytest.mark.parametrize(
    ("status", "subject_text", "body_text"),
    [
        (
            HardwareRequest.Status.PARTIALLY_RETURNED,
            "partially returned",
            "partially returned",
        ),
        (
            HardwareRequest.Status.RETURNED,
            "returned",
            "fully returned and closed",
        ),
        (
            HardwareRequest.Status.CLOSED_WITH_ISSUE,
            "closed with issue",
            "closed with damaged or missing items",
        ),
    ],
)
def test_hardware_return_staff_email_has_status_specific_wording(
    status,
    subject_text,
    body_text,
    django_capture_on_commit_callbacks,
):
    reset_outbox()
    makerspace = make_space(f"staff-hardware-return-{status}")
    staff = make_staff_user(
        f"staff-hardware-return-{status}-manager",
        makerspace,
        MakerspaceMembership.Role.INVENTORY_MANAGER,
        email=f"hardware-return-{status}@example.com",
    )
    product = make_product(makerspace)
    actor = make_user(
        f"staff-hardware-return-{status}-actor",
        access_status=User.AccessStatus.ACTIVE,
    )
    hardware_request = make_issued_request(makerspace, actor, [(product, 1)])
    hardware_request.status = status
    hardware_request.save(update_fields=["status", "updated_at"])

    # Return notifications deliver async (dispatch_email -> on_commit -> Celery task);
    # fire the commit hooks so the eager task actually sends.
    with django_capture_on_commit_callbacks(execute=True):
        hardware_notifications.notify_request_returned(hardware_request)

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [staff.email]
    assert subject_text in mail.outbox[0].subject
    assert body_text in mail.outbox[0].body


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_notify_return_due_returns_original_boolean_and_emails_staff():
    reset_outbox()
    makerspace = make_space("staff-hardware-return-due")
    staff = make_staff_user(
        "staff-hardware-return-due-manager",
        makerspace,
        MakerspaceMembership.Role.INVENTORY_MANAGER,
        email="hardware-return-due-staff@example.com",
    )
    product = make_product(makerspace)
    actor = make_member("staff-hardware-return-due-actor", makerspace)
    hardware_request = make_issued_request(makerspace, actor, [(product, 1)])
    hardware_request.requester_contact_email = "hardware-return-due-requester@example.com"
    hardware_request.return_due_at = timezone.now()
    hardware_request.save(
        update_fields=["requester_contact_email", "return_due_at", "updated_at"]
    )

    assert hardware_notifications.notify_return_due(hardware_request) is True
    assert_address_sent("hardware-return-due-requester@example.com")
    assert_address_sent(staff.email)


def test_notify_return_due_true_when_only_staff_reminded_no_borrower_email():
    # Regression (Codex Stage-4 P2): when staff notifications are on but the borrower has
    # no reachable email, the staff reminder is sent — and notify_return_due must report
    # True so the cron marks return_reminder_sent_at and does NOT re-send the staff reminder
    # every run.
    reset_outbox()
    makerspace = make_space("staff-hardware-return-due-no-borrower")
    staff = make_staff_user(
        "staff-hardware-return-due-no-borrower-manager",
        makerspace,
        MakerspaceMembership.Role.INVENTORY_MANAGER,
        email="hardware-return-due-no-borrower-staff@example.com",
    )
    product = make_product(makerspace)
    actor = make_member("staff-hardware-return-due-no-borrower-actor", makerspace)
    hardware_request = make_issued_request(makerspace, actor, [(product, 1)])
    hardware_request.requester_contact_email = ""
    hardware_request.return_due_at = timezone.now()
    hardware_request.save(
        update_fields=["requester_contact_email", "return_due_at", "updated_at"]
    )

    assert hardware_notifications.notify_return_due(hardware_request) is True
    assert_address_sent(staff.email)


def test_notify_return_due_false_when_nobody_reachable():
    # No borrower email AND staff notifications disabled -> nothing reminded -> False, so the
    # cron leaves the row unmarked and retries (correct: no spam, no silent drop).
    reset_outbox()
    makerspace = make_space("staff-hardware-return-due-nobody")
    makerspace.staff_notifications_enabled = False
    makerspace.save(update_fields=["staff_notifications_enabled"])
    product = make_product(makerspace)
    actor = make_member("staff-hardware-return-due-nobody-actor", makerspace)
    hardware_request = make_issued_request(makerspace, actor, [(product, 1)])
    hardware_request.requester_contact_email = ""
    hardware_request.return_due_at = timezone.now()
    hardware_request.save(
        update_fields=["requester_contact_email", "return_due_at", "updated_at"]
    )

    assert hardware_notifications.notify_return_due(hardware_request) is False
    assert mail.outbox == []


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_public_print_submit_emails_printing_staff_once(
    django_capture_on_commit_callbacks,
):
    reset_outbox()
    makerspace = make_space("staff-print-public-submit")
    bucket = make_bucket(makerspace)
    staff = make_print_manager("staff-print-public-submit-manager", makerspace)
    staff.email = "print-public-submit-staff@example.com"
    staff.save(update_fields=["email"])

    with django_capture_on_commit_callbacks(execute=True):
        response = APIClient().post(
            public_print_submit_url(makerspace),
            {
                "identifier": "print-public-submit",
                "bucket_id": bucket.id,
                "title": "Public bracket",
                "contact_email": "print-public-requester@example.com",
            },
            format="json",
        )

    assert response.status_code == 201
    assert_address_sent("print-public-requester@example.com")
    assert_address_count(staff.email, 1)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_authenticated_print_submit_emails_printing_staff_once(
    django_capture_on_commit_callbacks,
):
    reset_outbox()
    makerspace = make_space("staff-print-auth-submit")
    bucket = make_bucket(makerspace)
    requester = make_user(
        "staff-print-auth-requester",
        access_status=User.AccessStatus.ACTIVE,
    )
    staff = make_print_manager("staff-print-auth-submit-manager", makerspace)
    staff.email = "print-auth-submit-staff@example.com"
    staff.save(update_fields=["email"])

    with django_capture_on_commit_callbacks(execute=True):
        response = print_authenticated_client(requester).post(
            print_request_list_url(),
            {
                "bucket": bucket.id,
                "title": "Authenticated bracket",
                "quantity": 1,
            },
            format="json",
        )

    assert response.status_code == 201
    assert_address_count(staff.email, 1)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
@pytest.mark.parametrize(
    ("event", "initial_status", "call"),
    [
        (
            "accepted",
            PrintRequest.Status.PENDING,
            lambda req, actor: print_workflow.accept(req, actor),
        ),
        (
            "started",
            PrintRequest.Status.ACCEPTED,
            lambda req, actor: print_workflow.start(req, actor),
        ),
        (
            "completed",
            PrintRequest.Status.PRINTING,
            lambda req, actor: print_workflow.complete(req, actor),
        ),
        (
            "rejected",
            PrintRequest.Status.PENDING,
            lambda req, actor: print_workflow.reject(req, actor, "Too fragile."),
        ),
        (
            "failed",
            PrintRequest.Status.PRINTING,
            lambda req, actor: print_workflow.fail(req, actor, "Nozzle jammed."),
        ),
        (
            "collected",
            PrintRequest.Status.COMPLETED,
            lambda req, actor: print_workflow.mark_collected(req, actor),
        ),
    ],
)
def test_printing_transition_events_email_printing_staff_once(
    event,
    initial_status,
    call,
    django_capture_on_commit_callbacks,
):
    reset_outbox()
    makerspace = make_space(f"staff-print-{event}")
    bucket = make_bucket(makerspace)
    requester = make_user(
        f"staff-print-{event}-requester",
        access_status=User.AccessStatus.ACTIVE,
        email=f"staff-print-{event}-requester@example.com",
    )
    staff = make_print_manager(f"staff-print-{event}-manager", makerspace)
    staff.email = f"staff-print-{event}-staff@example.com"
    staff.save(update_fields=["email"])
    print_request = make_print_request(
        bucket,
        requester,
        title=f"{event} bracket",
        status=initial_status,
    )

    with django_capture_on_commit_callbacks(execute=True):
        call(print_request, staff)

    assert_address_count(staff.email, 1)
    assert any(event in message.subject for message in mail.outbox if staff.email in message.to)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_printing_reprint_emits_staff_reprinted_email(
    django_capture_on_commit_callbacks,
):
    reset_outbox()
    makerspace = make_space("staff-print-reprint")
    bucket = make_bucket(makerspace)
    requester = make_user("staff-print-reprint-requester", access_status=User.AccessStatus.ACTIVE)
    staff = make_print_manager("staff-print-reprint-manager", makerspace)
    staff.email = "staff-print-reprint-staff@example.com"
    staff.save(update_fields=["email"])
    failed = make_print_request(
        bucket,
        requester,
        title="Failed bracket",
        status=PrintRequest.Status.FAILED,
    )

    with django_capture_on_commit_callbacks(execute=True):
        clone = print_workflow.reprint(failed, staff)

    assert clone.status == PrintRequest.Status.ACCEPTED
    assert_address_count(staff.email, 1)
    assert "reprint request" in mail.outbox[0].subject
    assert "reprinted" in mail.outbox[0].body


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_hardware_staff_send_failure_does_not_block_transition_or_requester_email(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    reset_outbox()
    makerspace = make_space("staff-hardware-fail-safe")
    product = make_product(makerspace)
    admin = make_member("staff-hardware-fail-safe-admin", makerspace)
    make_staff_user(
        "staff-hardware-fail-safe-manager",
        makerspace,
        MakerspaceMembership.Role.INVENTORY_MANAGER,
        email="hardware-fail-safe-staff@example.com",
    )
    hardware_request = make_accepted_request(makerspace, product, 1)
    hardware_request.status = HardwareRequest.Status.PENDING_APPROVAL
    hardware_request.requester_contact_email = "hardware-fail-safe-requester@example.com"
    hardware_request.save(update_fields=["status", "requester_contact_email", "updated_at"])
    product.available_quantity += 1
    product.reserved_quantity -= 1
    product.save(update_fields=["available_quantity", "reserved_quantity", "updated_at"])

    def fail_staff_send(*args, **kwargs):
        raise RuntimeError("staff SMTP failed")

    monkeypatch.setattr(
        "apps.hardware_requests.staff_notifications.send_makerspace_email",
        fail_staff_send,
    )

    with django_capture_on_commit_callbacks(execute=True):
        response = hardware_authenticated_client(admin).post(
            accept_url(hardware_request),
            format="json",
        )

    assert response.status_code == 200
    hardware_request.refresh_from_db()
    assert hardware_request.status == HardwareRequest.Status.ACCEPTED
    assert recipient_addresses() == ["hardware-fail-safe-requester@example.com"]


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_printing_staff_resolver_failure_does_not_block_transition_or_requester_email(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    reset_outbox()
    makerspace = make_space("staff-print-fail-safe")
    bucket = make_bucket(makerspace)
    requester = make_user(
        "staff-print-fail-safe-requester",
        access_status=User.AccessStatus.ACTIVE,
        email="print-fail-safe-requester@example.com",
    )
    manager = make_print_manager("staff-print-fail-safe-manager", makerspace)
    print_request = make_print_request(bucket, requester)

    def fail_resolver(*args, **kwargs):
        raise RuntimeError("resolver failed")

    monkeypatch.setattr("apps.printing.emails.staff_emails_for_stream", fail_resolver)

    with django_capture_on_commit_callbacks(execute=True):
        response = print_authenticated_client(manager).post(
            print_action_url(print_request, "accept"),
            format="json",
        )

    assert response.status_code == 200
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.ACCEPTED
    assert recipient_addresses() == ["print-fail-safe-requester@example.com"]


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_notify_return_due_keeps_boolean_when_staff_send_fails(monkeypatch):
    reset_outbox()
    makerspace = make_space("staff-return-due-fail-safe")
    staff = make_staff_user(
        "staff-return-due-fail-safe-manager",
        makerspace,
        MakerspaceMembership.Role.INVENTORY_MANAGER,
        email="return-due-fail-safe-staff@example.com",
    )
    product = make_product(makerspace)
    actor = make_member("staff-return-due-fail-safe-actor", makerspace)
    hardware_request = make_issued_request(makerspace, actor, [(product, 1)])
    hardware_request.requester_contact_email = "return-due-fail-safe-requester@example.com"
    hardware_request.save(update_fields=["requester_contact_email", "updated_at"])

    def fail_staff_send(*args, **kwargs):
        raise RuntimeError("staff SMTP failed")

    monkeypatch.setattr(
        "apps.hardware_requests.staff_notifications.send_makerspace_email",
        fail_staff_send,
    )

    assert hardware_notifications.notify_return_due(hardware_request) is True
    assert recipient_addresses() == ["return-due-fail-safe-requester@example.com"]
    assert staff.email not in recipient_addresses()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_staff_notification_toggle_disables_staff_but_keeps_requester_email(
    django_capture_on_commit_callbacks,
):
    reset_outbox()
    makerspace = make_space("staff-toggle-disabled")
    makerspace.staff_notifications_enabled = False
    makerspace.save(update_fields=["staff_notifications_enabled"])
    product = make_product(makerspace)
    admin = make_member("staff-toggle-disabled-admin", makerspace)
    staff = make_staff_user(
        "staff-toggle-disabled-manager",
        makerspace,
        MakerspaceMembership.Role.INVENTORY_MANAGER,
        email="toggle-disabled-staff@example.com",
    )
    hardware_request = make_accepted_request(makerspace, product, 1)
    hardware_request.status = HardwareRequest.Status.PENDING_APPROVAL
    hardware_request.requester_contact_email = "toggle-disabled-requester@example.com"
    hardware_request.save(update_fields=["status", "requester_contact_email", "updated_at"])
    product.available_quantity += 1
    product.reserved_quantity -= 1
    product.save(update_fields=["available_quantity", "reserved_quantity", "updated_at"])

    with django_capture_on_commit_callbacks(execute=True):
        response = hardware_authenticated_client(admin).post(
            accept_url(hardware_request),
            format="json",
        )

    assert response.status_code == 200
    assert recipient_addresses() == ["toggle-disabled-requester@example.com"]
    assert staff.email not in recipient_addresses()


def test_staff_emails_excludes_opted_out_manager():
    makerspace = make_space("notif-optout")
    keep = make_staff_user("notif-keep", makerspace, MakerspaceMembership.Role.SPACE_MANAGER)
    drop = make_staff_user("notif-drop", makerspace, MakerspaceMembership.Role.INVENTORY_MANAGER)
    MakerspaceMembership.objects.filter(makerspace=makerspace, user=drop).update(
        receives_notifications=False,
    )

    emails = staff_emails_for_stream(makerspace, "hardware")

    assert keep.email in emails
    assert drop.email not in emails


def test_notification_recipients_endpoint_lists_and_toggles():
    makerspace = make_space("notif-endpoint")
    manager = make_staff_user("notif-mgr", makerspace, MakerspaceMembership.Role.SPACE_MANAGER)
    other = make_staff_user("notif-other", makerspace, MakerspaceMembership.Role.PRINT_MANAGER)
    client = hardware_authenticated_client(manager)
    url = f"/api/v1/admin/makerspace/{makerspace.id}/notification-recipients"

    listed = client.get(url)
    assert listed.status_code == 200
    by_user = {row["username"]: row for row in listed.data}
    assert by_user["notif-other"]["receives_notifications"] is True
    other_membership_id = by_user["notif-other"]["id"]

    patched = client.patch(
        url,
        {"recipients": [{"id": other_membership_id, "receives_notifications": False}]},
        format="json",
    )
    assert patched.status_code == 200
    membership = MakerspaceMembership.objects.get(id=other_membership_id)
    assert membership.receives_notifications is False
    assert other.email not in staff_emails_for_stream(makerspace, "printing")
