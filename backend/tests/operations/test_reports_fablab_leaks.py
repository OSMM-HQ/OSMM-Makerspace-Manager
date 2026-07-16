from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.bookings.models import BookableSpace, Booking
from apps.events.models import Event, EventRegistration
from apps.machines.models import Machine, MachineType, MachineUsageEntry
from apps.maintenance.models import MaintenanceLog, MaintenanceLogDocument, MaintenanceSchedule
from apps.operations import reports
from tests.return_helpers import make_member, make_space


pytestmark = pytest.mark.django_db


def test_private_identity_notes_locations_and_keys_never_enter_report_payloads():
    sentinel = "PRIVATE-SENTINEL-9f33"
    space = make_space("analytics-leaks")
    manager = make_member("analytics-leak-manager", space)
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

    for key in ("machine-usage", "event-attendance", "booking-utilization", "maintenance-activity", "fablab-health"):
        payload = reports.report_data(key, space.id)
        assert sentinel not in repr(payload)
        forbidden = {"note", "logged_by", "email", "phone", "public_token", "summary", "parts_note", "performed_by", "object_key", "location"}
        assert not forbidden.intersection(_keys(payload))


def _keys(value):
    if isinstance(value, dict):
        return set(value) | {key for child in value.values() for key in _keys(child)}
    if isinstance(value, (list, tuple)):
        return {key for child in value for key in _keys(child)}
    return set()
