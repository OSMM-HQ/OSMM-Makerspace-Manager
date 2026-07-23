"""Lifecycle notification adapter for events and registrations."""

from django.utils import formats, timezone

from apps.events.models import Event, EventRegistration
from apps.integrations.notify import EmailDelivery, LifecyclePayload, notify_lifecycle
from apps.integrations.staff_notifications import staff_emails_for_feature


def _when(event):
    starts_at = timezone.localtime(event.starts_at)
    ends_at = timezone.localtime(event.ends_at)
    return (
        f"{formats.date_format(starts_at, 'DATETIME_FORMAT')} to "
        f"{formats.date_format(ends_at, 'DATETIME_FORMAT')}"
    )


def _text(event, event_name, registration=None):
    lines = [
        f"Event #{event.pk} {event_name}.",
        f"Title: {event.title}",
        f"Time: {_when(event)}",
        f"Status: {event.status}",
    ]
    if event.location:
        lines.append(f"Location: {event.location}")
    if registration is not None:
        lines.extend(
            (
                f"Registration: #{registration.pk}",
                f"Registrant: {registration.name}",
                f"Registration status: {registration.status}",
            )
        )
    return "\n".join(lines)


def notify_event_lifecycle(
    event_obj, event_name, registration_id=None, *, sync=False
):
    event_id = event_obj.pk
    makerspace = event_obj.makerspace

    def build():
        event = Event.objects.select_related("makerspace").get(pk=event_id)
        registration = None
        if registration_id is not None:
            registration = EventRegistration.objects.get(
                pk=registration_id,
                event=event,
            )
        text = _text(event, event_name, registration)
        subject = f"{makerspace.name} event #{event.pk} {event_name}"
        emails = tuple(
            EmailDelivery(
                to_email=recipient,
                subject=subject,
                text_body=text,
                audience="staff",
                stream="events",
            )
            for recipient in staff_emails_for_feature(
                makerspace, "events", event=event_name
            )
        )
        return LifecyclePayload(text=text, emails=emails)

    return notify_lifecycle(
        makerspace,
        feature="events",
        event=event_name,
        build=build,
        sync=sync,
    )
