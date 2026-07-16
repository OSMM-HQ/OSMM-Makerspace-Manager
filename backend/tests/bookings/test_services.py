from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.db import close_old_connections, connection
from django.utils import timezone
from rest_framework.serializers import ValidationError

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.bookings import services
from apps.bookings.exceptions import BookingConflict, BookingInvalidTransition
from apps.bookings.models import BookableSpace, Booking
from apps.hardware_requests.exceptions import workflow_exception_handler
from apps.makerspaces.models import Makerspace

pytestmark = pytest.mark.django_db


def make_makerspace(slug='booking-services'):
    return Makerspace.objects.create(name=slug, slug=slug)


def make_actor(name='booking-manager'):
    return User.objects.create_user(username=name)

def make_space(makerspace=None, actor=None, **overrides):
    values = dict(
        makerspace=makerspace or make_makerspace(), actor=actor,
        name='Development Room', kind=BookableSpace.Kind.DEV_ROOM,
        description='', capacity=8, location='', is_public=True,
    )
    values.update(overrides)
    return services.create_space(**values)


def book(space, start=None, **overrides):
    start = start or timezone.now() + timedelta(hours=1)
    values = dict(
        name='Ada Lovelace', email='ada@example.com', phone='123',
        starts_at=start, ends_at=start + timedelta(hours=1), note='',
    )
    values.update(overrides)
    return services.create_booking(space, **values)


def direct_booking(space, status=Booking.Status.BOOKED, **overrides):
    start = overrides.pop('starts_at', timezone.now() - timedelta(hours=2))
    values = dict(
        space=space, name='Guest', email='guest@example.com', phone='123',
        starts_at=start, ends_at=start + timedelta(hours=1), status=status,
    )
    values.update(overrides)
    return Booking.objects.create(**values)


def assert_error(exc, code):
    response = workflow_exception_handler(exc, {})
    assert response.status_code == 409
    assert response.data == {'detail': str(exc), 'code': code}

def test_space_workflows_allow_only_contract_fields_and_audit():
    makerspace, actor = make_makerspace(), make_actor()
    space = make_space(makerspace, actor, name='  Lab  ')
    assert (space.name, space.created_by, space.is_active) == ('Lab', actor, True)
    updated = services.update_space(
        space, actor=actor, name='Studio', kind=BookableSpace.Kind.OTHER,
        description='Shared', capacity=12, location='L1', is_public=False,
    )
    assert updated.name == 'Studio' and updated.capacity == 12
    for field, value in (
        ('makerspace', make_makerspace('other')), ('created_by', None),
        ('image_key', 'raw/key'), ('public_token', space.public_token),
        ('is_active', False), ('unknown', 'value'),
    ):
        with pytest.raises(ValidationError):
            services.update_space(updated, actor=actor, **{field: value})
    deactivated = services.deactivate_space(updated, actor=actor)
    assert deactivated.is_active is False
    assert list(AuditLog.objects.values_list('action', flat=True)) == [
        'booking.space_deactivated', 'booking.space_updated',
        'booking.space_created',
    ]
    assert set(AuditLog.objects.values_list('target_type', flat=True)) == {
        'bookings.bookablespace'
    }

def test_inactive_space_is_terminal_and_preserves_bookings():
    space, actor = make_space(), make_actor()
    existing = book(space)
    services.deactivate_space(space, actor=actor)
    before = AuditLog.objects.count()
    for operation in (
        lambda: services.update_space(space, actor=actor, name='No'),
        lambda: services.deactivate_space(space, actor=actor),
        lambda: book(space),
    ):
        with pytest.raises(BookingInvalidTransition) as caught:
            operation()
        assert_error(caught.value, 'invalid_transition')
    existing.refresh_from_db()
    assert existing.status == Booking.Status.BOOKED
    assert AuditLog.objects.count() == before


def test_booking_normalizes_identity_and_has_pii_free_exact_audit_target():
    space = make_space()
    booking = book(
        space, name='  Ada Lovelace  ', email='  ADA@Example.COM  ',
        phone='  123  ', note='private note',
    )
    log = AuditLog.objects.get(action='booking.created')
    assert (booking.name, booking.email, booking.phone, booking.status) == (
        'Ada Lovelace', 'ada@example.com', '123', Booking.Status.BOOKED,
    )
    assert (log.target_type, log.makerspace) == ('bookings.booking', space.makerspace)
    serialized = str(log.meta).lower()
    assert all(value not in serialized for value in ('ada', '123', 'private note'))


def test_overlap_conflict_response_has_no_row_or_audit_and_adjacency_works():
    space = make_space()
    start = timezone.now() + timedelta(hours=2)
    first = book(space, start)
    before = AuditLog.objects.count()
    with pytest.raises(BookingConflict) as caught:
        book(space, start + timedelta(minutes=30))
    assert_error(caught.value, 'booking_conflict')
    assert Booking.objects.filter(space=space).count() == 1
    assert AuditLog.objects.count() == before
    adjacent = book(space, first.ends_at)
    for starts_at, ends_at in (
        (start + timedelta(minutes=10), start + timedelta(minutes=20)),
        (start, first.ends_at),
        (start - timedelta(minutes=10), first.ends_at + timedelta(minutes=10)),
    ):
        with pytest.raises(BookingConflict):
            book(space, starts_at, ends_at=ends_at)
    assert adjacent.status == Booking.Status.BOOKED

def test_terminal_rows_do_not_block_interval_reuse():
    start = timezone.now() + timedelta(hours=1)
    for index, status in enumerate(
        (Booking.Status.CANCELLED, Booking.Status.COMPLETED, Booking.Status.NO_SHOW)
    ):
        space = make_space(make_makerspace(f'terminal-{index}'))
        direct_booking(space, status, starts_at=start, ends_at=start + timedelta(hours=1))
        assert book(space, start).status == Booking.Status.BOOKED


@pytest.mark.django_db(transaction=True)
def test_postgres_concurrent_overlap_has_one_winner_and_spaces_are_independent(monkeypatch):
    space = make_space()
    start = timezone.now() + timedelta(hours=1)
    gate = Barrier(2)
    def race(target):
        close_old_connections(); gate.wait()
        try:
            book(BookableSpace.objects.get(pk=target.pk), start)
            return 'created'
        except BookingConflict:
            return 'conflict'
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(race, (space, space))) == ['conflict', 'created']
    assert Booking.objects.filter(space=space).count() == 1

    spaces = (make_space(make_makerspace('parallel-a')), make_space(make_makerspace('parallel-b')))
    original_record, audit_gate = services.audit.record, Barrier(2)
    def synchronized_audit(*args, **kwargs):
        audit_gate.wait(timeout=5)
        return original_record(*args, **kwargs)
    monkeypatch.setattr(services.audit, 'record', synchronized_audit)
    gate = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(race, spaces)) == ['created', 'created']

@pytest.mark.django_db(transaction=True)
def test_deactivation_and_create_serialize_on_the_space():
    space, actor, gate = make_space(), make_actor(), Barrier(2)
    def run(operation):
        close_old_connections(); gate.wait()
        target = BookableSpace.objects.get(pk=space.pk)
        try:
            if operation == 'deactivate':
                services.deactivate_space(target, actor=actor)
            else:
                book(target)
            return 'created' if operation == 'create' else 'deactivated'
        except BookingInvalidTransition:
            return 'inactive'
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(run, ('deactivate', 'create')))
    space.refresh_from_db()
    assert space.is_active is False
    assert outcomes in (['deactivated', 'inactive'], ['deactivated', 'created'])
    assert Booking.objects.filter(space=space).count() == (outcomes[1] == 'created')

def test_frozen_clock_booking_and_lifecycle_boundaries(monkeypatch):
    now = timezone.now()
    current = [now]
    monkeypatch.setattr(services.timezone, 'now', lambda: current[0])
    space = make_space()
    before = AuditLog.objects.count()
    with pytest.raises(ValidationError):
        book(space, now - timedelta(minutes=1), ends_at=now)
    assert not Booking.objects.filter(space=space).exists()
    assert AuditLog.objects.count() == before
    allowed = book(
        space, now - timedelta(minutes=1), ends_at=now + timedelta(microseconds=1)
    )
    assert allowed.starts_at < now < allowed.ends_at

    for operation in (services.complete_booking, services.mark_no_show):
        row = direct_booking(space, ends_at=now + timedelta(hours=1))
        current[0] = row.ends_at - timedelta(microseconds=1)
        with pytest.raises(BookingInvalidTransition):
            operation(row, actor=None)
        current[0] = row.ends_at
        result = operation(row, actor=None)
        expected = Booking.Status.COMPLETED if operation is services.complete_booking else Booking.Status.NO_SHOW
        assert result.status == expected


def test_lifecycle_transitions_audit_and_terminal_states_are_exact_conflicts():
    space, actor = make_space(), make_actor()
    rows = [
        direct_booking(space, starts_at=timezone.now() - timedelta(hours=2))
        for _ in range(3)
    ]
    terminal = (
        services.cancel_booking(rows[0], actor=actor),
        services.complete_booking(rows[1], actor=actor),
        services.mark_no_show(rows[2], actor=actor),
    )
    assert [row.status for row in terminal] == ['cancelled', 'completed', 'no_show']
    assert {'booking.cancelled', 'booking.completed', 'booking.no_show_marked'} <= set(
        AuditLog.objects.values_list('action', flat=True)
    )
    before = AuditLog.objects.count()
    for row in terminal:
        for operation in (services.cancel_booking, services.complete_booking, services.mark_no_show):
            with pytest.raises(BookingInvalidTransition) as caught:
                operation(row, actor=actor)
            assert_error(caught.value, 'invalid_transition')
    assert AuditLog.objects.count() == before


def test_lifecycle_locks_space_before_booking_and_revalidates_stale_rows():
    space = make_space()
    row = direct_booking(space)
    locks = []
    def capture(execute, sql, params, many, context):
        if 'FOR UPDATE' in sql:
            locks.append(sql)
        return execute(sql, params, many, context)
    with connection.execute_wrapper(capture):
        services.cancel_booking(row, actor=None)
    assert 'bookings_bookablespace' in locks[0]
    assert 'bookings_booking' in locks[1]
    stale = direct_booking(space)
    Booking.objects.filter(pk=stale.pk).update(status=Booking.Status.COMPLETED)
    with pytest.raises(BookingInvalidTransition):
        services.cancel_booking(stale, actor=None)

@pytest.mark.parametrize('operation', [
    'create_space', 'update_space', 'deactivate_space', 'create_booking',
    'cancel_booking', 'complete_booking', 'mark_no_show',
])
def test_mocked_audit_failure_rolls_back_every_mutation(monkeypatch, operation):
    makerspace, actor = make_makerspace(), make_actor()
    space = make_space(makerspace, actor)
    row = direct_booking(space)
    before = (BookableSpace.objects.count(), Booking.objects.count())
    calls = {
        'create_space': lambda: make_space(makerspace, actor, name='New'),
        'update_space': lambda: services.update_space(space, actor=actor, name='Changed'),
        'deactivate_space': lambda: services.deactivate_space(space, actor=actor),
        'create_booking': lambda: book(space),
        'cancel_booking': lambda: services.cancel_booking(row, actor=actor),
        'complete_booking': lambda: services.complete_booking(row, actor=actor),
        'mark_no_show': lambda: services.mark_no_show(row, actor=actor),
    }
    monkeypatch.setattr(services.audit, 'record', lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    with pytest.raises(RuntimeError):
        calls[operation]()
    space.refresh_from_db(); row.refresh_from_db()
    assert (BookableSpace.objects.count(), Booking.objects.count()) == before
    assert (space.name, space.is_active, row.status) == ('Development Room', True, 'booked')


def test_bookings_have_no_quota_or_image_service_code():
    from apps.makerspaces import limits
    source = open(services.__file__, encoding='utf-8').read()
    assert all(term not in source for term in ('check_quota', 'limits', 'image'))
    assert all('bookings' not in mapping for mapping in (limits.KNOWN_LIMIT_KEYS, limits.RESOURCE_LABELS, limits._COUNTERS))
