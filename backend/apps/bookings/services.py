'''Audited mutation boundary for bookable spaces and bookings.'''

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.audit import services as audit
from apps.bookings.exceptions import BookingConflict, BookingInvalidTransition
from apps.bookings.models import BookableSpace, Booking
from apps.makerspaces.models import Makerspace

SPACE_FIELDS = frozenset(
    {'name', 'kind', 'description', 'capacity', 'location', 'is_public'}
)


def _locked_space(space_id):
    return (
        BookableSpace.objects.select_for_update()
        .select_related('makerspace')
        .get(pk=space_id)
    )


def _validate(instance):
    try:
        instance.full_clean(validate_unique=False, validate_constraints=False)
    except DjangoValidationError as exc:
        detail = exc.message_dict if hasattr(exc, 'message_dict') else exc.messages
        raise serializers.ValidationError(detail) from exc
    if isinstance(instance, Booking) and instance.ends_at <= instance.starts_at:
        raise serializers.ValidationError(
            {'ends_at': 'End time must be after start time.'}
        )


def _audit(space, actor, action, target, meta=None):
    return audit.record(
        actor,
        action,
        makerspace=space.makerspace,
        target=target,
        meta=meta or {},
    )


def _refresh(instance):
    instance.refresh_from_db()
    return instance


@transaction.atomic
def create_space(
    *, makerspace, actor, name, kind, description, capacity, location, is_public
):
    locked_makerspace = Makerspace.objects.select_for_update().get(pk=makerspace.pk)
    space = BookableSpace(
        makerspace=locked_makerspace,
        created_by=actor,
        name=name,
        kind=kind,
        description=description,
        capacity=capacity,
        location=location,
        is_public=is_public,
        is_active=True,
    )
    _validate(space)
    space.save()
    _audit(space, actor, 'booking.space_created', space)
    return _refresh(space)


@transaction.atomic
def update_space(space, *, actor, **changes):
    locked = _locked_space(space.pk)
    if not locked.is_active:
        raise BookingInvalidTransition('Inactive spaces cannot be updated.')
    unknown = set(changes) - SPACE_FIELDS
    if unknown:
        raise serializers.ValidationError(
            {field: 'This field cannot be updated.' for field in sorted(unknown)}
        )

    for field, value in changes.items():
        setattr(locked, field, value)
    _validate(locked)
    if changes:
        locked.save(update_fields=[*sorted(changes), 'updated_at'])
    _audit(
        locked,
        actor,
        'booking.space_updated',
        locked,
        {'changed_fields': sorted(changes)},
    )
    return _refresh(locked)


@transaction.atomic
def deactivate_space(space, *, actor):
    locked = _locked_space(space.pk)
    if not locked.is_active:
        raise BookingInvalidTransition('Space is already inactive.')
    locked.is_active = False
    locked.save(update_fields=['is_active', 'updated_at'])
    _audit(
        locked,
        actor,
        'booking.space_deactivated',
        locked,
        {'old_status': 'active', 'new_status': 'inactive'},
    )
    return _refresh(locked)


@transaction.atomic
def create_booking(
    space, *, name, email, phone, starts_at, ends_at, note='', actor=None
):
    locked_space = _locked_space(space.pk)
    if not locked_space.is_active:
        raise BookingInvalidTransition('Inactive spaces cannot accept bookings.')

    now = timezone.now()
    booking = Booking(
        space=locked_space,
        name=(name or '').strip(),
        email=(email or '').strip().lower(),
        phone=(phone or '').strip(),
        starts_at=starts_at,
        ends_at=ends_at,
        note=note,
        status=Booking.Status.BOOKED,
    )
    _validate(booking)
    if ends_at <= now:
        raise serializers.ValidationError(
            {'ends_at': 'End time must be in the future.'}
        )
    if Booking.objects.filter(
        space=locked_space,
        status=Booking.Status.BOOKED,
        starts_at__lt=ends_at,
        ends_at__gt=starts_at,
    ).exists():
        raise BookingConflict('This space is already booked for that time.')

    booking.save()
    _audit(
        locked_space,
        actor,
        'booking.created',
        booking,
        {'booking_id': booking.pk, 'status': Booking.Status.BOOKED},
    )
    return _refresh(booking)


def _locked_booking(booking):
    space = _locked_space(booking.space_id)
    locked = Booking.objects.select_for_update().get(pk=booking.pk)
    if locked.space_id != space.pk:
        raise BookingInvalidTransition('Booking no longer belongs to this space.')
    return space, locked


def _transition(booking, actor, new_status, action, *, require_ended=False):
    space, locked = _locked_booking(booking)
    if locked.status != Booking.Status.BOOKED:
        raise BookingInvalidTransition(
            f'Cannot transition booking from {locked.status} to {new_status}.'
        )
    if require_ended and locked.ends_at > timezone.now():
        raise BookingInvalidTransition('Booking has not ended yet.')
    old_status = locked.status
    locked.status = new_status
    locked.save(update_fields=['status'])
    _audit(
        space,
        actor,
        action,
        locked,
        {
            'booking_id': locked.pk,
            'old_status': old_status,
            'new_status': new_status,
        },
    )
    return _refresh(locked)


@transaction.atomic
def cancel_booking(booking, *, actor):
    return _transition(
        booking, actor, Booking.Status.CANCELLED, 'booking.cancelled'
    )


@transaction.atomic
def complete_booking(booking, *, actor):
    return _transition(
        booking,
        actor,
        Booking.Status.COMPLETED,
        'booking.completed',
        require_ended=True,
    )


@transaction.atomic
def mark_no_show(booking, *, actor):
    return _transition(
        booking,
        actor,
        Booking.Status.NO_SHOW,
        'booking.no_show_marked',
        require_ended=True,
    )
