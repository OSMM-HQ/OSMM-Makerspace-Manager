import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction

from apps.integrations.email import makerspace_mail_connection, send_makerspace_email
from apps.integrations.email_templates import printing_context, render
from apps.integrations.staff_notifications import staff_emails_for_stream
from apps.printing.models import PrintRequest

logger = logging.getLogger(__name__)


def _with_email_relations(print_request):
    bucket_cached = "bucket" in print_request._state.fields_cache
    makerspace_cached = (
        bucket_cached and "makerspace" in print_request.bucket._state.fields_cache
    )
    requester_cached = "requester" in print_request._state.fields_cache
    if bucket_cached and makerspace_cached and requester_cached:
        return print_request
    return (
        type(print_request)
        .objects.select_related("bucket__makerspace", "requester")
        .get(pk=print_request.pk)
    )


def _request_for_email(request_id):
    return PrintRequest.objects.select_related("bucket__makerspace", "requester").get(
        pk=request_id
    )


def queue_print_email(event, request_id):
    transaction.on_commit(
        lambda event=event, request_id=request_id: send_print_email(
            event, _request_for_email(request_id)
        )
    )


def queue_staff_print_email(event, request_id):
    transaction.on_commit(
        lambda event=event, request_id=request_id: send_staff_print_email(
            event, _request_for_email(request_id)
        )
    )


def send_print_email(event, print_request):
    print_request = _with_email_relations(print_request)
    # Public requests come from Check-In shadow users with no account email, so the
    # reachable address is the contact_email captured on the request; fall back to the
    # requester's account email for staff-created/authenticated requests.
    recipient = print_request.contact_email or print_request.requester.email
    if not recipient:
        return

    makerspace = print_request.bucket.makerspace
    base = getattr(settings, "PUBLIC_APP_BASE_URL", "") or ""
    status_url = (
        f"{base}/m/{makerspace.slug}/print?token={print_request.public_token}"
        if base
        else ""
    )
    try:
        rendered = render(
            makerspace,
            "printing",
            "requester",
            event,
            printing_context(print_request, status_url, print_request.public_token),
        )
        connection, from_email = makerspace_mail_connection(makerspace)
        message = EmailMultiAlternatives(
            subject=rendered["subject"],
            body=rendered["text_body"],
            from_email=from_email,
            to=[recipient],
            connection=connection,
        )
        if rendered["html_body"]:
            message.attach_alternative(rendered["html_body"], "text/html")
        message.send()
    except Exception:
        logger.warning(
            "print_email_send_failed",
            extra={
                "event": event,
                "print_request_id": print_request.pk,
                "requester_id": print_request.requester_id,
            },
            exc_info=True,
        )


def send_staff_print_email(event, print_request):
    try:
        print_request = _with_email_relations(print_request)
        makerspace = print_request.bucket.makerspace
        recipients = staff_emails_for_stream(makerspace, "printing")
        if not recipients:
            return

        rendered = render(
            makerspace,
            "printing",
            "staff",
            event,
            printing_context(print_request, "", ""),
        )
        send_makerspace_email(
            makerspace,
            rendered["subject"],
            rendered["text_body"],
            recipients,
        )
    except Exception:
        logger.warning(
            "print_staff_email_send_failed",
            extra={
                "event": event,
                "print_request_id": getattr(print_request, "pk", None),
            },
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
