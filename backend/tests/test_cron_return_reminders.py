from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem
from apps.inventory.models import InventoryProduct
from apps.makerspaces.models import Makerspace

pytestmark = pytest.mark.django_db

CRON_URL = "/api/v1/internal/cron/return-reminders"


def make_user(username, role=User.Role.REQUESTER, **kw):
    return get_user_model().objects.create_user(
        username=username,
        email=f"{username}@e.com",
        role=role,
        **kw,
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


def make_overdue_request(makerspace, product):
    requester = make_user(
        f"cron-reminder-{makerspace.slug}",
        access_status=User.AccessStatus.ACTIVE,
    )
    hardware_request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        requester_contact_email="cron-reminder@example.com",
        status=HardwareRequest.Status.ISSUED,
        return_due_at=timezone.now() - timedelta(minutes=5),
    )
    HardwareRequestItem.objects.create(
        request=hardware_request,
        product=product,
        requested_quantity=1,
        accepted_quantity=1,
        issued_quantity=1,
    )
    return hardware_request


@override_settings(CRON_SECRET="")
def test_return_reminder_cron_is_404_when_secret_unset():
    response = APIClient().post(CRON_URL, format="json")

    assert response.status_code == 404


@override_settings(CRON_SECRET="s3cr3t")
def test_return_reminder_cron_requires_matching_secret():
    client = APIClient()

    missing = client.post(CRON_URL, format="json")
    wrong = client.post(CRON_URL, HTTP_X_CRON_SECRET="wrong", format="json")
    correct = client.post(CRON_URL, HTTP_X_CRON_SECRET="s3cr3t", format="json")

    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert correct.status_code == 200
    assert isinstance(correct.data["sent"], int)
    assert isinstance(correct.data["skipped"], int)


@override_settings(CRON_SECRET="s3cr3t")
def test_return_reminder_cron_sends_due_reminder_and_marks_request(monkeypatch):
    makerspace = make_space("cron-reminder")
    product = make_product(makerspace)
    hardware_request = make_overdue_request(makerspace, product)
    monkeypatch.setattr(
        "apps.hardware_requests.notifications.notify_return_due",
        lambda request: True,
    )

    response = APIClient().post(
        CRON_URL,
        HTTP_X_CRON_SECRET="s3cr3t",
        format="json",
    )

    assert response.status_code == 200
    assert response.data["sent"] >= 1
    hardware_request.refresh_from_db()
    assert hardware_request.return_reminder_sent_at is not None
