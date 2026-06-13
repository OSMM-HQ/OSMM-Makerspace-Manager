from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem
from apps.inventory.models import InventoryProduct
from apps.makerspaces.models import Makerspace

pytestmark = pytest.mark.django_db


def make_user(username, role=User.Role.REQUESTER, **kw):
    return get_user_model().objects.create_user(
        username=username, email=f"{username}@e.com", role=role, **kw
    )


def make_space(slug):
    return Makerspace.objects.create(name=slug, slug=slug)


def make_product(makerspace):
    return InventoryProduct.objects.create(
        makerspace=makerspace,
        name=f"Product {makerspace.slug}",
        total_quantity=1,
        available_quantity=0,
        issued_quantity=1,
        is_public=True,
    )


def make_request(makerspace, product, *, status, contact_email, due_at):
    requester = make_user(
        f"reminder-{makerspace.slug}-{status}-{contact_email.split('@')[0]}",
        access_status=User.AccessStatus.ACTIVE,
    )
    hardware_request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        requester_contact_email=contact_email,
        status=status,
        return_due_at=due_at,
    )
    HardwareRequestItem.objects.create(
        request=hardware_request,
        product=product,
        requested_quantity=1,
        accepted_quantity=1,
        issued_quantity=1,
    )
    return hardware_request


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_send_return_reminders_emails_only_overdue_active_unreminded_requests(mailoutbox):
    now = timezone.now()
    makerspace = make_space("return-reminders")
    product = make_product(makerspace)
    overdue = make_request(
        makerspace,
        product,
        status=HardwareRequest.Status.ISSUED,
        contact_email="overdue@example.com",
        due_at=now - timedelta(minutes=5),
    )
    returned = make_request(
        makerspace,
        product,
        status=HardwareRequest.Status.RETURNED,
        contact_email="returned@example.com",
        due_at=now - timedelta(days=1),
    )
    future = make_request(
        makerspace,
        product,
        status=HardwareRequest.Status.ISSUED,
        contact_email="future@example.com",
        due_at=now + timedelta(days=1),
    )

    out = StringIO()
    call_command("send_return_reminders", stdout=out)

    assert "Return reminders sent: 1" in out.getvalue()
    assert [message.to for message in mailoutbox] == [["overdue@example.com"]]
    assert "return reminder" in mailoutbox[0].subject
    overdue.refresh_from_db()
    returned.refresh_from_db()
    future.refresh_from_db()
    assert overdue.return_reminder_sent_at is not None
    assert returned.return_reminder_sent_at is None
    assert future.return_reminder_sent_at is None

    call_command("send_return_reminders", stdout=StringIO())
    assert len(mailoutbox) == 1
