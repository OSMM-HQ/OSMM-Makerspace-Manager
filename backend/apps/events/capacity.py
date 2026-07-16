import math

from apps.events.models import EventRegistration


CONFIRMED_STATUSES = (
    EventRegistration.Status.REGISTERED,
    EventRegistration.Status.ATTENDED,
)


def confirmed_occupancy(event):
    confirmed = getattr(event, 'confirmed_count', None)
    if confirmed is None:
        confirmed = event.registrations.filter(
            status__in=CONFIRMED_STATUSES
        ).count()
    return confirmed


def spots_left(event):
    if event.capacity == 0:
        return None
    return max(event.capacity - confirmed_occupancy(event), 0)


def availability_label(event):
    if event.capacity == 0:
        return 'Available'
    left = spots_left(event)
    if left <= 0:
        return 'Full'
    if left <= math.ceil(event.capacity * 0.2):
        return 'Limited'
    return 'Available'


def fresh_registration_status(event):
    available = spots_left(event)
    if available is None or available > 0:
        return EventRegistration.Status.REGISTERED
    return EventRegistration.Status.WAITLISTED
