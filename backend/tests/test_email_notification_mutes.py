import pytest
from django.test import override_settings

from apps.integrations.email_templates_registry import (
    HARDWARE_REQUESTER_KEYS,
    HARDWARE_STAFF_KEYS,
    PRINTING_REQUESTER_KEYS,
    PRINTING_STAFF_KEYS,
)
from apps.integrations.models import EmailLog, EmailNotificationMute
from apps.integrations.notification_rules import (
    ALWAYS_ON,
    EVENT_CATALOG,
    is_event_mutable,
    is_requester_muted,
    muted_targets,
    role_muted,
    valid_targets_for_stream,
)
from apps.integrations.staff_notifications import staff_emails_for_stream
from apps.hardware_requests import notifications as hardware_notifications
from apps.makerspaces.models import MakerspaceMembership
from apps.printing.emails import send_print_email
from tests.test_issue import make_accepted_request, make_product, make_space
from tests.test_printing import make_bucket, make_request as make_print_request, make_user
from tests.test_staff_notifications import make_staff_user

pytestmark = pytest.mark.django_db
Role = MakerspaceMembership.Role


def create_mute(makerspace, *, target, stream, event, audience):
    return EmailNotificationMute.objects.create(
        makerspace=makerspace,
        target=target,
        stream=stream,
        event=event,
        audience=audience,
    )


def mutable_keys(keys):
    return tuple(key for key in keys if key != "return_reminder")


def test_event_catalog_matches_template_registry_minus_always_on_keys():
    assert EVENT_CATALOG[("hardware", "requester")] == mutable_keys(HARDWARE_REQUESTER_KEYS)
    assert EVENT_CATALOG[("hardware", "staff")] == mutable_keys(HARDWARE_STAFF_KEYS)
    assert EVENT_CATALOG[("printing", "requester")] == mutable_keys(PRINTING_REQUESTER_KEYS)
    assert EVENT_CATALOG[("printing", "staff")] == mutable_keys(PRINTING_STAFF_KEYS)
    assert ALWAYS_ON == frozenset({"return_reminder"})
    assert all("return_reminder" not in events for events in EVENT_CATALOG.values())


@pytest.mark.parametrize(
    ("stream", "audience", "event"),
    [
        ("hardware", "requester", "request_accepted"),
        ("hardware", "staff", "partially_returned"),
        ("printing", "staff", "collected"),
        ("printing", "staff", "reprinted"),
    ],
)
def test_is_event_mutable_returns_true_for_catalog_events(stream, audience, event):
    assert is_event_mutable(stream, audience, event) is True


@pytest.mark.parametrize(
    ("stream", "audience", "event"),
    [
        ("hardware", "requester", "return_reminder"),
        ("hardware", "staff", "return_reminder"),
        ("hardware", "requester", "missing_event"),
        ("missing_stream", "requester", "request_accepted"),
    ],
)
def test_is_event_mutable_returns_false_for_always_on_and_unknown_events(stream, audience, event):
    assert is_event_mutable(stream, audience, event) is False


def test_role_muted_checks_matching_staff_role_event_and_never_always_on():
    makerspace = make_space("mute-role")
    role = Role.INVENTORY_MANAGER

    assert role_muted(makerspace, "hardware", "accepted", role) is False

    create_mute(
        makerspace,
        target=role.value,
        stream="hardware",
        event="accepted",
        audience="staff",
    )
    create_mute(
        makerspace,
        target=role.value,
        stream="hardware",
        event="return_reminder",
        audience="staff",
    )

    assert role_muted(makerspace, "hardware", "accepted", role) is True
    assert role_muted(makerspace, "hardware", "accepted", Role.SPACE_MANAGER) is False
    assert role_muted(makerspace, "hardware", "issued", role) is False
    assert role_muted(makerspace, "hardware", "return_reminder", role) is False


def test_is_requester_muted_checks_matching_requester_event_and_never_always_on():
    makerspace = make_space("mute-requester")

    assert is_requester_muted(makerspace, "hardware", "request_accepted") is False

    create_mute(
        makerspace,
        target="requester",
        stream="hardware",
        event="request_accepted",
        audience="requester",
    )
    create_mute(
        makerspace,
        target="requester",
        stream="hardware",
        event="return_reminder",
        audience="requester",
    )

    assert is_requester_muted(makerspace, "hardware", "request_accepted") is True
    assert is_requester_muted(makerspace, "hardware", "return_reminder") is False


def test_muted_targets_returns_valid_muted_targets_across_mutable_audiences():
    makerspace = make_space("mute-targets")
    create_mute(
        makerspace,
        target="requester",
        stream="printing",
        event="accepted",
        audience="requester",
    )
    create_mute(
        makerspace,
        target=Role.SPACE_MANAGER.value,
        stream="printing",
        event="accepted",
        audience="staff",
    )
    create_mute(
        makerspace,
        target=Role.MACHINE_MANAGER.value,
        stream="printing",
        event="accepted",
        audience="staff",
    )
    create_mute(
        makerspace,
        target=Role.INVENTORY_MANAGER.value,
        stream="printing",
        event="accepted",
        audience="staff",
    )

    assert muted_targets(makerspace, "printing", "accepted") == {
        "requester",
        Role.SPACE_MANAGER.value,
        Role.MACHINE_MANAGER.value,
    }
    assert muted_targets(makerspace, "hardware", "return_reminder") == set()


def test_valid_targets_for_stream_lists_requester_and_stream_roles():
    assert valid_targets_for_stream("hardware") == ("requester", Role.SPACE_MANAGER.value, Role.INVENTORY_MANAGER.value)
    assert valid_targets_for_stream("printing") == ("requester", Role.SPACE_MANAGER.value, Role.MACHINE_MANAGER.value)
    assert valid_targets_for_stream("unknown") == ()


def test_staff_role_mute_excludes_hardware_role_only_when_event_is_supplied():
    makerspace = make_space("mute-staff-hardware")
    space_manager = make_staff_user(
        "mute-hardware-space",
        makerspace,
        Role.SPACE_MANAGER,
        email="hardware-space@example.com",
    )
    inventory_manager = make_staff_user(
        "mute-hardware-inventory",
        makerspace,
        Role.INVENTORY_MANAGER,
        email="hardware-inventory@example.com",
    )
    create_mute(makerspace, target=Role.INVENTORY_MANAGER.value, stream="hardware", event="accepted", audience="staff")

    assert staff_emails_for_stream(makerspace, "hardware", event="accepted") == [
        space_manager.email
    ]
    assert staff_emails_for_stream(makerspace, "hardware", event=None) == [
        space_manager.email,
        inventory_manager.email,
    ]


def test_staff_role_mute_excludes_printing_role_only_when_event_is_supplied():
    makerspace = make_space("mute-staff-printing")
    space_manager = make_staff_user(
        "mute-print-space",
        makerspace,
        Role.SPACE_MANAGER,
        email="print-space@example.com",
    )
    print_manager = make_staff_user(
        "mute-print-manager",
        makerspace,
        Role.MACHINE_MANAGER,
        email="print-manager@example.com",
    )
    create_mute(makerspace, target=Role.MACHINE_MANAGER.value, stream="printing", event="started", audience="staff")

    assert staff_emails_for_stream(makerspace, "printing", event="started") == [
        space_manager.email
    ]
    assert staff_emails_for_stream(makerspace, "printing", event=None) == [
        space_manager.email,
        print_manager.email,
    ]


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_hardware_requester_mute_skips_email_log_and_unmuted_send_logs_email(
    django_capture_on_commit_callbacks,
):
    makerspace = make_space("mute-hardware-requester")
    product = make_product(makerspace)
    hardware_request = make_accepted_request(makerspace, product, 1)
    hardware_request.requester_contact_email = "hardware-requester@example.com"
    hardware_request.save(update_fields=["requester_contact_email", "updated_at"])
    create_mute(makerspace, target="requester", stream="hardware", event="request_accepted", audience="requester")

    with django_capture_on_commit_callbacks(execute=True):
        hardware_notifications.notify_request_accepted(hardware_request)
    assert EmailLog.objects.count() == 0

    EmailNotificationMute.objects.all().delete()
    with django_capture_on_commit_callbacks(execute=True):
        hardware_notifications.notify_request_accepted(hardware_request)
    log = EmailLog.objects.get()
    assert log.to_email == "hardware-requester@example.com"
    assert log.stream == "hardware"
    assert log.event == "request_accepted"
    assert log.audience == "requester"
    assert log.status == EmailLog.Status.SENT


def test_printing_requester_mute_skips_email_log():
    makerspace = make_space("mute-print-requester")
    bucket = make_bucket(makerspace)
    requester = make_user(
        "mute-print-requester-user",
        access_status="active",
    )
    print_request = make_print_request(bucket, requester)
    create_mute(makerspace, target="requester", stream="printing", event="accepted", audience="requester")

    send_print_email("accepted", print_request)

    assert EmailLog.objects.count() == 0


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_return_reminder_requester_email_ignores_bogus_mute_row():
    makerspace = make_space("mute-return-reminder")
    product = make_product(makerspace)
    hardware_request = make_accepted_request(makerspace, product, 1)
    hardware_request.requester_contact_email = "return-reminder@example.com"
    hardware_request.save(update_fields=["requester_contact_email", "updated_at"])
    create_mute(makerspace, target="requester", stream="hardware", event="return_reminder", audience="requester")

    assert hardware_notifications.notify_return_due(hardware_request) is True
    log = EmailLog.objects.get()
    assert log.to_email == "return-reminder@example.com"
    assert log.event == "return_reminder"
    assert log.status == EmailLog.Status.SENT
