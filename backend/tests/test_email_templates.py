import pytest
from django.contrib.auth import get_user_model

from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem
from apps.integrations.email_templates import hardware_context, printing_context, render
from apps.integrations.models import EmailTemplate
from apps.inventory.models import InventoryProduct
from apps.makerspaces.models import Makerspace
from apps.printing.models import PrintBucket, PrintRequest

pytestmark = pytest.mark.django_db


def make_user(username, **kwargs):
    return get_user_model().objects.create_user(
        username=username,
        email=kwargs.pop("email", f"{username}@example.com"),
        **kwargs,
    )


def make_space(slug, **kwargs):
    defaults = {"name": slug, "slug": slug}
    defaults.update(kwargs)
    return Makerspace.objects.create(**defaults)


def make_product(makerspace, name="Oscilloscope"):
    return InventoryProduct.objects.create(
        makerspace=makerspace,
        name=name,
        description=f"{name} description",
        total_quantity=5,
        available_quantity=5,
        is_public=True,
    )


def make_hardware_request(makerspace, requester=None):
    requester = requester or make_user(f"{makerspace.slug}-requester")
    request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        requester_contact_email=f"{requester.username}@contact.example",
        requester_contact_phone="+15550101010",
        requested_for="Workshop repair",
    )
    HardwareRequestItem.objects.create(
        request=request,
        product=make_product(makerspace),
        requested_quantity=2,
        issued_quantity=1,
    )
    return request


def make_print_request(makerspace, requester=None, **kwargs):
    requester = requester or make_user(f"{makerspace.slug}-print-requester")
    bucket = PrintBucket.objects.create(makerspace=makerspace, name="General")
    defaults = {
        "bucket": bucket,
        "requester": requester,
        "title": "Replacement bracket",
        "quantity": 1,
    }
    defaults.update(kwargs)
    return PrintRequest.objects.create(**defaults)


def test_render_uses_active_db_row_and_default_when_missing():
    makerspace = make_space("row-render")
    hardware_request = make_hardware_request(makerspace)
    EmailTemplate.objects.create(
        makerspace=makerspace,
        stream="hardware",
        audience="requester",
        key="request_received",
        subject="Custom {{ request.id }}",
        text_body="Hello {{ request.requester_username }}",
        html_body="<p>{{ makerspace.name }}</p>",
    )

    rendered = render(
        makerspace,
        "hardware",
        "requester",
        "request_received",
        hardware_context(hardware_request, staff=False),
    )
    default_rendered = render(
        makerspace,
        "hardware",
        "requester",
        "request_accepted",
        hardware_context(hardware_request, staff=False),
    )

    assert rendered == {
        "subject": f"Custom {hardware_request.id}",
        "text_body": f"Hello {hardware_request.requester_username}",
        "html_body": f"<p>{makerspace.name}</p>",
    }
    assert default_rendered["subject"] == f"{makerspace.name} request approved"
    assert "has been approved" in default_rendered["text_body"]


def test_render_falls_back_to_default_when_stored_row_raises():
    makerspace = make_space("row-fallback")
    hardware_request = make_hardware_request(makerspace)
    EmailTemplate.objects.create(
        makerspace=makerspace,
        stream="hardware",
        audience="requester",
        key="request_received",
        subject="{% if %}",
        text_body="Custom body",
    )

    rendered = render(
        makerspace,
        "hardware",
        "requester",
        "request_received",
        hardware_context(hardware_request, staff=False),
    )

    assert rendered["subject"] == f"{makerspace.name} request received"
    assert "Your makerspace request" in rendered["text_body"]


def test_sanitized_context_blocks_secret_and_relation_access():
    makerspace = make_space("sanitized")
    makerspace.set_smtp_password("super-secret")
    makerspace.save(update_fields=["smtp_password"])
    hardware_request = make_hardware_request(makerspace)
    EmailTemplate.objects.create(
        makerspace=makerspace,
        stream="hardware",
        audience="requester",
        key="request_received",
        subject="Sanitized",
        text_body=(
            "secret={{ makerspace.get_smtp_password }} "
            "relation={{ request.requester.email }}"
        ),
    )

    rendered = render(
        makerspace,
        "hardware",
        "requester",
        "request_received",
        hardware_context(hardware_request, staff=False),
    )

    assert rendered["text_body"] == "secret= relation="
    assert "super-secret" not in rendered["text_body"]
    assert hardware_request.requester.email not in rendered["text_body"]


def test_printing_staff_default_uses_requester_account_email_when_contact_blank():
    makerspace = make_space("printing-staff-email")
    requester = make_user("print-account", email="account@example.com")
    print_request = make_print_request(
        makerspace,
        requester=requester,
        requester_name="",
        contact_email="",
    )

    rendered = render(
        makerspace,
        "printing",
        "staff",
        "submitted",
        printing_context(print_request, "", ""),
    )

    assert "Email: account@example.com" in rendered["text_body"]


def test_hardware_staff_render_includes_staff_summary():
    makerspace = make_space("hardware-staff-summary")
    hardware_request = make_hardware_request(makerspace)

    rendered = render(
        makerspace,
        "hardware",
        "staff",
        "submitted",
        hardware_context(hardware_request, staff=True),
    )

    assert "A new hardware request needs review." in rendered["text_body"]
    assert f"Requester: {hardware_request.requester_username}" in rendered["text_body"]
    assert "Status: pending_approval" in rendered["text_body"]
