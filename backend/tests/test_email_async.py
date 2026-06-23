from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.db import connection
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.hardware_requests import notifications as hardware_notifications
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem
from apps.integrations import tasks as email_tasks
from apps.integrations.dispatch import dispatch_email
from apps.integrations.models import EmailLog
from apps.integrations.tasks import deliver_email_task
from apps.inventory.models import InventoryProduct
from apps.makerspaces.models import Makerspace, MakerspaceMembership

pytestmark = pytest.mark.django_db

def make_space(slug, **kwargs):
    return Makerspace.objects.create(name=slug, slug=slug, **kwargs)

def make_user(username, **kwargs):
    return get_user_model().objects.create_user(
        username=username,
        email=kwargs.pop("email", f"{username}@example.com"),
        access_status=kwargs.pop("access_status", User.AccessStatus.ACTIVE),
        **kwargs,
    )

def make_member(username, makerspace, role=MakerspaceMembership.Role.SPACE_MANAGER):
    user = make_user(username, role=User.Role.SPACE_MANAGER)
    MakerspaceMembership.objects.create(user=user, makerspace=makerspace, role=role)
    return user

def make_product(makerspace):
    return InventoryProduct.objects.create(
        makerspace=makerspace,
        name=f"Product {makerspace.slug}",
        total_quantity=1,
        available_quantity=0,
        issued_quantity=1,
        is_public=True,
    )

def make_issued_request(makerspace, requester, product):
    hardware_request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        requester_contact_email="borrower@example.com",
        status=HardwareRequest.Status.ISSUED,
        return_due_at=timezone.now(),
    )
    HardwareRequestItem.objects.create(
        request=hardware_request,
        product=product,
        requested_quantity=1,
        accepted_quantity=1,
        issued_quantity=1,
    )
    return hardware_request

def authenticated_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client

def retry_url(log):
    return f"/api/v1/admin/makerspace/{log.makerspace_id}/email-logs/{log.id}/retry"

@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_async_dispatch_delivers_after_commit(django_capture_on_commit_callbacks):
    makerspace = make_space("email-async-dispatch")

    with django_capture_on_commit_callbacks(execute=True):
        log = dispatch_email(
            to_email="borrower@example.com",
            subject="Ready",
            text_body="Your item is ready.",
            makerspace=makerspace,
            stream="hardware",
            event="request_accepted",
            audience="requester",
        )

    log.refresh_from_db()
    assert log.status == EmailLog.Status.SENT
    assert log.sent_at is not None
    assert log.attempts == 1

def test_async_dispatch_records_forced_send_failure(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    makerspace = make_space("email-async-failure")

    def fail_send(self):
        raise RuntimeError("smtp unavailable")

    monkeypatch.setattr(EmailMultiAlternatives, "send", fail_send)

    with django_capture_on_commit_callbacks(execute=True):
        log = dispatch_email(
            to_email="borrower@example.com",
            subject="Ready",
            text_body="Your item is ready.",
            makerspace=makerspace,
        )

    log.refresh_from_db()
    assert log.status == EmailLog.Status.FAILED
    assert log.sent_at is None
    assert log.attempts >= 1

@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_return_reminder_path_stays_synchronous():
    makerspace = make_space("email-async-return-reminder")
    staff = make_member(
        "email-async-return-reminder-manager",
        makerspace,
        MakerspaceMembership.Role.INVENTORY_MANAGER,
    )
    staff.email = "staff@example.com"
    staff.save(update_fields=["email"])
    requester = make_member("email-async-return-reminder-requester", makerspace)
    hardware_request = make_issued_request(makerspace, requester, make_product(makerspace))

    assert hardware_notifications.notify_return_due(hardware_request) is True
    # Borrower + staff reminders all deliver synchronously (the borrower here is also a
    # Space Manager, so they're additionally a staff recipient — hence >= 2, not == 2).
    # The load-bearing assertion is that NOTHING is left pending (i.e. nothing went async).
    assert EmailLog.objects.filter(status=EmailLog.Status.SENT).count() >= 2
    assert EmailLog.objects.filter(status=EmailLog.Status.PENDING).count() == 0

@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_retry_endpoint_reenqueues_failed_log(django_capture_on_commit_callbacks):
    makerspace = make_space("email-async-retry")
    manager = make_member("email-async-retry-manager", makerspace)
    log = EmailLog.objects.create(
        makerspace=makerspace,
        to_email="borrower@example.com",
        subject="Retry me",
        text_body="Stored retry body",
        status=EmailLog.Status.FAILED,
        error="smtp unavailable",
    )

    with django_capture_on_commit_callbacks(execute=True):
        response = authenticated_client(manager).post(retry_url(log), format="json")

    assert response.status_code == 200
    log.refresh_from_db()
    assert log.status == EmailLog.Status.SENT
    assert log.error == ""
    assert log.attempts == 1
    # Every state-changing endpoint must emit an audit entry (repo invariant).
    from apps.audit.models import AuditLog

    assert AuditLog.objects.filter(action="email.retried", target_id=str(log.pk)).exists()

def test_retry_endpoint_scopes_cross_tenant_and_hidden_makerspaces():
    own_space = make_space("email-async-retry-own")
    other_space = make_space("email-async-retry-other")
    hidden_space = make_space(
        "email-async-retry-hidden",
        superadmin_access_enabled=False,
    )
    manager = make_member("email-async-retry-own-manager", own_space)
    superadmin = make_user(
        "email-async-retry-superadmin",
        role=User.Role.SUPERADMIN,
        is_staff=True,
        is_superuser=True,
    )
    other_log = EmailLog.objects.create(
        makerspace=other_space,
        to_email="other@example.com",
        subject="Other",
        text_body="Stored body",
        status=EmailLog.Status.FAILED,
    )
    hidden_log = EmailLog.objects.create(
        makerspace=hidden_space,
        to_email="hidden@example.com",
        subject="Hidden",
        text_body="Stored body",
        status=EmailLog.Status.FAILED,
    )

    assert authenticated_client(manager).post(retry_url(other_log)).status_code == 404
    assert authenticated_client(superadmin).post(retry_url(hidden_log)).status_code == 404

def test_retry_endpoint_rejects_non_failed_and_redacted_logs():
    makerspace = make_space("email-async-retry-rejects")
    manager = make_member("email-async-retry-rejects-manager", makerspace)
    sent_log = EmailLog.objects.create(
        makerspace=makerspace,
        to_email="sent@example.com",
        subject="Sent",
        text_body="Stored body",
        status=EmailLog.Status.SENT,
    )
    redacted = EmailLog.objects.create(
        makerspace=makerspace,
        to_email="redacted@example.com",
        subject="Redacted",
        status=EmailLog.Status.FAILED,
    )
    client = authenticated_client(manager)

    assert client.post(retry_url(sent_log)).status_code == 400
    assert client.post(retry_url(redacted)).status_code == 400

@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_deliver_email_task_releases_lock_before_smtp(monkeypatch):
    makerspace = make_space("email-async-lock-release")
    log = EmailLog.objects.create(
        makerspace=makerspace,
        to_email="borrower@example.com",
        subject="Ready",
        text_body="Stored body",
    )
    observed_atomic_state = []
    outer_atomic_depth = len(connection.savepoint_ids)

    def fake_deliver(claimed_log):
        observed_atomic_state.append(len(connection.savepoint_ids))
        claimed_log.status = EmailLog.Status.SENT
        claimed_log.error = ""
        claimed_log.save(update_fields=["status", "error", "updated_at"])
        return claimed_log

    monkeypatch.setattr("apps.integrations.tasks._deliver", fake_deliver)

    deliver_email_task(log.id)

    assert observed_atomic_state == [outer_atomic_depth]
    log.refresh_from_db()
    assert log.status == EmailLog.Status.SENT



def test_email_retry_countdown_uses_backoff_and_jitter(monkeypatch):
    monkeypatch.setattr(email_tasks.random, "randint", lambda low, high: high)

    assert email_tasks._retry_countdown(0) == 90
    assert email_tasks._retry_countdown(1) == 150
    assert email_tasks._retry_countdown(5) == 930

def test_claim_skips_fresh_sending_and_reclaims_stale_sending(monkeypatch):
    monkeypatch.setattr(email_tasks, "email_task_hard_limit", lambda: 60)
    log = EmailLog.objects.create(
        to_email="borrower@example.com",
        subject="Claim",
        text_body="Stored body",
        status=EmailLog.Status.SENDING,
        error="old",
    )

    assert email_tasks._claim_log(log.id) is None

    EmailLog.objects.filter(pk=log.pk).update(
        updated_at=timezone.now() - timedelta(seconds=66),
    )
    claimed = email_tasks._claim_log(log.id)

    assert claimed is not None
    assert claimed.status == EmailLog.Status.SENDING
    assert claimed.error == ""
