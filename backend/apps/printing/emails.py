import logging

from django.conf import settings

from apps.integrations import notification_rules
from apps.integrations.dispatch import dispatch_email
from apps.integrations.email import send_makerspace_email
from apps.integrations.email_templates import printing_context, render
from apps.integrations.notify import EmailDelivery, LifecyclePayload, notify_lifecycle
from apps.integrations.staff_notifications import (
    staff_emails_for_feature,
    staff_emails_for_stream,
)
from apps.printing.models import PrintRequest

logger = logging.getLogger(__name__)
REQUESTER_EVENTS = frozenset({"submitted", "accepted", "started", "rejected", "completed"})


def _with_email_relations(print_request):
    bucket_cached = "bucket" in print_request._state.fields_cache
    makerspace_cached = (
        bucket_cached and "makerspace" in print_request.bucket._state.fields_cache
    )
    requester_cached = "requester" in print_request._state.fields_cache
    if bucket_cached and makerspace_cached and requester_cached:
        return print_request
    return PrintRequest.objects.select_related("bucket__makerspace", "requester").get(
        pk=print_request.pk
    )


def _request_for_email(request_id):
    return PrintRequest.objects.select_related("bucket__makerspace", "requester").get(
        pk=request_id
    )


def _requester_render(event, print_request):
    recipient = print_request.contact_email or print_request.requester.email
    if not recipient:
        return None, None
    makerspace = print_request.bucket.makerspace
    base = getattr(settings, "PUBLIC_APP_BASE_URL", "") or ""
    status_url = (
        f"{base}/m/{makerspace.slug}/print?token={print_request.public_token}"
        if base
        else ""
    )
    rendered = render(
        makerspace,
        "printing",
        "requester",
        event,
        printing_context(print_request, status_url, print_request.public_token),
    )
    return recipient, rendered


def _staff_render(event, print_request):
    return render(
        print_request.bucket.makerspace,
        "printing",
        "staff",
        event,
        printing_context(print_request, "", ""),
    )


def notify_print_status(print_request, event, *, sync=False):
    request_id = print_request.pk
    makerspace = print_request.bucket.makerspace

    def build():
        row = _request_for_email(request_id)
        emails = []
        if event in REQUESTER_EVENTS:
            recipient, rendered = _requester_render(event, row)
            if recipient:
                emails.append(
                    EmailDelivery(
                        to_email=recipient,
                        subject=rendered["subject"],
                        text_body=rendered["text_body"],
                        html_body=rendered["html_body"],
                        audience="requester",
                        target="requester",
                        stream="printing",
                        mute_event=event,
                    )
                )
        recipients = staff_emails_for_feature(makerspace, "printing", event=event)
        if recipients:
            rendered = _staff_render(event, row)
            emails.extend(
                EmailDelivery(
                    to_email=recipient,
                    subject=rendered["subject"],
                    text_body=rendered["text_body"],
                    html_body=rendered["html_body"],
                    audience="staff",
                    stream="printing",
                    mute_event=event,
                )
                for recipient in recipients
            )
        return LifecyclePayload(text=_staff_print_body(event, row), emails=tuple(emails))

    return notify_lifecycle(
        makerspace,
        feature="printing",
        event=event,
        build=build,
        sync=sync,
    )


def send_print_email(event, print_request):
    """Compatibility direct requester-email adapter."""
    print_request = _with_email_relations(print_request)
    makerspace = print_request.bucket.makerspace
    if notification_rules.is_requester_muted(makerspace, "printing", event):
        return
    recipient, rendered = _requester_render(event, print_request)
    if not recipient:
        return
    try:
        dispatch_email(
            makerspace=makerspace,
            stream="printing",
            event=event,
            audience="requester",
            to_email=recipient,
            subject=rendered["subject"],
            text_body=rendered["text_body"],
            html_body=rendered["html_body"],
        )
    except Exception:
        logger.warning(
            "print_email_send_failed",
            extra={"event": event, "print_request_id": print_request.pk},
            exc_info=True,
        )


def send_staff_print_email(event, print_request):
    """Compatibility direct staff-email adapter."""
    try:
        print_request = _with_email_relations(print_request)
        makerspace = print_request.bucket.makerspace
        recipients = staff_emails_for_stream(makerspace, "printing", event=event)
        if not recipients:
            return
        rendered = _staff_render(event, print_request)
        send_makerspace_email(
            makerspace,
            rendered["subject"],
            rendered["text_body"],
            recipients,
            html_body=rendered["html_body"],
            stream="printing",
            event=event,
            audience="staff",
        )
    except Exception:
        logger.warning(
            "print_staff_email_send_failed",
            extra={"event": event, "print_request_id": getattr(print_request, "pk", None)},
            exc_info=True,
        )


def _staff_print_body(event, print_request):
    lines = [
        f"Print request #{print_request.pk} {event}.",
        "",
        f"Status: {print_request.status}",
        f"Title: {print_request.title}",
        f"Requester: {print_request.requester_name or print_request.requester.username}",
    ]
    if print_request.contact_email:
        lines.append(f"Email: {print_request.contact_email}")
    elif print_request.requester.email:
        lines.append(f"Email: {print_request.requester.email}")
    if print_request.contact_phone:
        lines.append(f"Phone: {print_request.contact_phone}")
    if print_request.material:
        lines.append(f"Material: {print_request.material}")
    if print_request.color:
        lines.append(f"Color: {print_request.color}")
    lines.append(f"Quantity: {print_request.quantity}")
    if print_request.reason:
        lines.append(f"Reason: {print_request.reason}")
    if print_request.reprint_of_id:
        lines.append(f"Reprint of: #{print_request.reprint_of_id}")
    return "\n".join(lines)
