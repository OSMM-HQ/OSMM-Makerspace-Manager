'''Requester notification fan-out seam for booking status changes.'''

import logging

from django.db import transaction
from django.utils import formats, timezone

from apps.bookings.models import Booking
from apps.integrations.dispatch import dispatch_email

logger = logging.getLogger(__name__)

BOOKING_NOTIFICATION_EVENTS = frozenset({'submitted', 'confirmed', 'rejected'})


def _effective_toggle(booking):
    override = booking.space.requester_notifications_enabled
    if override is not None:
        return override
    return booking.space.makerspace.booking_requester_notifications_enabled


def _interval(booking):
    starts_at = timezone.localtime(booking.starts_at)
    ends_at = timezone.localtime(booking.ends_at)
    datetime_format = 'DATETIME_FORMAT'
    return (
        f'{formats.date_format(starts_at, datetime_format)} to '
        f'{formats.date_format(ends_at, datetime_format)}'
    )


def _message(booking, event):
    next_steps = {
        'submitted': (
            'Your request is awaiting staff review. We will contact you when '
            'its status changes.'
        ),
        'confirmed': (
            'Your booking is confirmed. Please contact the makerspace if your '
            'plans change.'
        ),
        'rejected': (
            'Your request was not approved. Please contact the makerspace if '
            'you have questions.'
        ),
    }
    makerspace = booking.space.makerspace
    subject = f'Booking {booking.status}: {booking.space.name}'
    body = '\n'.join(
        (
            f'Hello {booking.name},',
            '',
            makerspace.name,
            f'Space: {booking.space.name}',
            f'Time: {_interval(booking)}',
            f'Status: {booking.status}',
            '',
            next_steps[event],
        )
    )
    return subject, body


def _deliver_booking_status(booking_id, event):
    makerspace_id = None
    try:
        booking = (
            Booking.objects.select_related('space__makerspace')
            .get(pk=booking_id)
        )
        makerspace = booking.space.makerspace
        makerspace_id = makerspace.pk
        if not _effective_toggle(booking) or not booking.email:
            return
        subject, body = _message(booking, event)
        dispatch_email(
            makerspace=makerspace,
            stream='bookings',
            event=event,
            audience='requester',
            to_email=booking.email,
            subject=subject,
            text_body=body,
        )
    except Exception:
        logger.warning(
            'booking_requester_notification_failed',
            extra={
                'booking_id': booking_id,
                'makerspace_id': makerspace_id,
                'event': event,
            },
        )


def notify_booking_status(booking, event):
    '''Queue requester delivery for a submitted, confirmed, or rejected booking.'''
    if event not in BOOKING_NOTIFICATION_EVENTS:
        raise ValueError(f'Unsupported booking notification event: {event!r}.')
    booking_id = booking.pk
    transaction.on_commit(
        lambda booking_id=booking_id, event=event: _deliver_booking_status(
            booking_id, event
        )
    )
