"""Shared lifecycle adapter for booking notifications."""

from django.utils import formats, timezone

from apps.bookings.models import Booking
from apps.integrations.notify import EmailDelivery, LifecyclePayload, notify_lifecycle
from apps.integrations.staff_notifications import staff_emails_for_feature

BOOKING_NOTIFICATION_EVENTS = frozenset(
    {"created", "confirmed", "rejected", "cancelled", "completed", "no_show"}
)


def _effective_toggle(booking):
    override = booking.space.requester_notifications_enabled
    if override is not None:
        return override
    return booking.space.makerspace.booking_requester_notifications_enabled


def _interval(booking):
    starts_at = timezone.localtime(booking.starts_at)
    ends_at = timezone.localtime(booking.ends_at)
    return (
        f"{formats.date_format(starts_at, 'DATETIME_FORMAT')} to "
        f"{formats.date_format(ends_at, 'DATETIME_FORMAT')}"
    )


def _message(booking, event):
    next_steps = {
        "created": (
            "Your booking request was received. We will contact you if its "
            "status changes."
        ),
        "confirmed": (
            "Your booking is confirmed. Please contact the makerspace if your "
            "plans change."
        ),
        "rejected": (
            "Your request was not approved. Please contact the makerspace if "
            "you have questions."
        ),
        "cancelled": "Your booking has been cancelled.",
        "completed": "Your booking has been marked completed.",
        "no_show": "Your booking has been marked as a no-show.",
    }
    makerspace = booking.space.makerspace
    subject = f"Booking {booking.status}: {booking.space.name}"
    body = "\n".join(
        (
            f"Hello {booking.name},",
            "",
            makerspace.name,
            f"Space: {booking.space.name}",
            f"Time: {_interval(booking)}",
            f"Status: {booking.status}",
            "",
            next_steps[event],
        )
    )
    return subject, body


def _group_text(booking, event):
    return "\n".join(
        (
            f"Booking #{booking.pk} {event}.",
            f"Space: {booking.space.name}",
            f"Time: {_interval(booking)}",
            f"Status: {booking.status}",
            f"Booker: {booking.name}",
        )
    )


def notify_booking_status(booking, event, *, sync=False):
    booking_id = booking.pk
    makerspace = booking.space.makerspace

    def build():
        row = Booking.objects.select_related("space__makerspace").get(pk=booking_id)
        emails = []
        subject, body = _message(row, event)
        if _effective_toggle(row) and row.email:
            emails.append(
                EmailDelivery(
                    to_email=row.email,
                    subject=subject,
                    text_body=body,
                    audience="requester",
                    stream="bookings",
                )
            )
        staff_subject = f"{makerspace.name} booking #{row.pk} {event}"
        staff_body = _group_text(row, event)
        emails.extend(
            EmailDelivery(
                to_email=recipient,
                subject=staff_subject,
                text_body=staff_body,
                audience="staff",
                stream="bookings",
            )
            for recipient in staff_emails_for_feature(
                makerspace, "bookings", event=event
            )
        )
        return LifecyclePayload(text=staff_body, emails=tuple(emails))

    return notify_lifecycle(
        makerspace,
        feature="bookings",
        event=event,
        build=build,
        sync=sync,
    )
