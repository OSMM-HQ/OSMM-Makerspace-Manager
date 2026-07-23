from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.bookings.models import BookableSpace, Booking
from apps.events.models import Event, EventRegistration
from apps.machines.models import Machine, MachineType, MachineUsageEntry
from apps.maintenance.models import MaintenanceLog, MaintenanceLogDocument, MaintenanceSchedule
from apps.operations import reports
from tests.return_helpers import make_member, make_space


pytestmark = pytest.mark.django_db

KEYS = (
    "event-attendance",
    "booking-utilization",
    "maintenance-activity",
    "machine-usage",
    "fablab-health",
)


@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("scope", ["per-makerspace", "aggregate"])
def test_private_identity_notes_locations_and_keys_never_enter_json_payloads(key, scope):
    sentinel = "PRIVATE-SENTINEL-9f33"
    suffix = f"{key}-{scope}"
    space = make_space(f"leak-{suffix}")
    manager = make_member(f"leak-mgr-{suffix}", space)
    machine_type = MachineType.objects.create(makerspace=space, slug="leak-type", name="Safe type")
    machine = Machine.objects.create(makerspace=space, machine_type=machine_type, name="Safe machine", location=sentinel, notes=sentinel)
    MachineUsageEntry.objects.create(machine=machine, hours=Decimal("1.00"), note=sentinel, logged_by=manager)
    event = Event.objects.create(makerspace=space, title="Safe event", description=sentinel, location=sentinel, starts_at=timezone.now(), ends_at=timezone.now() + timedelta(hours=1))
    EventRegistration.objects.create(event=event, name=sentinel, email=f"{sentinel}@example.com", phone=sentinel)
    bookable = BookableSpace.objects.create(makerspace=space, name="Safe space", description=sentinel, location=sentinel)
    Booking.objects.create(space=bookable, name=sentinel, email=f"book-{sentinel}@example.com", phone=sentinel, note=sentinel, starts_at=timezone.now(), ends_at=timezone.now() + timedelta(hours=1))
    log = MaintenanceLog.objects.create(machine=machine, performed_by=manager, summary=sentinel, parts_note=sentinel, cost=Decimal("2.00"))
    MaintenanceSchedule.objects.create(machine=machine, description=sentinel, interval_days=1, next_due=timezone.localdate())
    MaintenanceLogDocument.objects.create(log=log, object_key=f"private/{sentinel}", size_bytes=1, uploaded_by=manager)

    payload = reports.report_data(key, None if scope == "aggregate" else space.id)
    assert sentinel not in repr(payload)
    forbidden = {"note", "logged_by", "email", "phone", "public_token", "summary", "parts_note", "performed_by", "object_key", "location"}
    assert not forbidden.intersection(_keys(payload))


@pytest.mark.parametrize("key", KEYS)
def test_aggregate_report_query_count_is_constant_as_tenants_and_children_grow(
    key,
    django_assert_num_queries,
):
    _seed_query_graph("query-small", child_count=1)
    with CaptureQueriesContext(connection) as captured:
        reports.report_data(key)
    small_count = len(captured)
    assert small_count > 0

    for index in range(3):
        _seed_query_graph(f"query-expanded-{index}", child_count=4)
    with django_assert_num_queries(small_count):
        reports.report_data(key)


def _seed_query_graph(slug, child_count):
    space = make_space(slug)
    machine_type = MachineType.objects.create(
        makerspace=space,
        slug=f"{slug}-type",
        name=f"{slug} type",
    )
    now = timezone.now()
    for index in range(child_count):
        machine = Machine.objects.create(
            makerspace=space,
            machine_type=machine_type,
            name=f"{slug} machine {index}",
        )
        MachineUsageEntry.objects.create(machine=machine, hours=Decimal("1.00"))
        event = Event.objects.create(
            makerspace=space,
            title=f"{slug} event {index}",
            starts_at=now + timedelta(hours=index),
            ends_at=now + timedelta(hours=index + 1),
        )
        EventRegistration.objects.create(
            event=event,
            name=f"{slug} attendee {index}",
            email=f"{slug}-{index}@example.com",
        )
        bookable = BookableSpace.objects.create(
            makerspace=space,
            name=f"{slug} space {index}",
        )
        Booking.objects.create(
            space=bookable,
            name=f"{slug} booker {index}",
            email=f"{slug}-booker-{index}@example.com",
            phone="555-0100",
            starts_at=now + timedelta(hours=index),
            ends_at=now + timedelta(hours=index + 1),
        )
        MaintenanceLog.objects.create(
            machine=machine,
            summary=f"{slug} log {index}",
            cost=Decimal("1.00"),
        )
        MaintenanceSchedule.objects.create(
            machine=machine,
            description=f"{slug} schedule {index}",
            interval_days=1,
            next_due=timezone.localdate(),
        )


def _keys(value):
    if isinstance(value, dict):
        return set(value) | {key for child in value.values() for key in _keys(child)}
    if isinstance(value, (list, tuple)):
        return {key for child in value for key in _keys(child)}
    return set()
