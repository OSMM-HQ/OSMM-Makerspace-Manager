import logging

from apps.integrations.email import send_makerspace_email
from apps.integrations.telegram import send_message

logger = logging.getLogger(__name__)


def notify_subdomain_request_resolved(subdomain_request):
    status = subdomain_request.status
    makerspace = subdomain_request.makerspace
    requester = subdomain_request.requested_by
    label = subdomain_request.requested_label

    subject = f"{makerspace.name} subdomain request {status}"
    body = f"Your subdomain request '{label}' for {makerspace.name} was {status}."
    if status == subdomain_request.Status.APPROVED:
        body = f"{body}\n\nYour new address is {makerspace.frontend_domain}."
    elif status == subdomain_request.Status.REJECTED and subdomain_request.note:
        body = f"{body}\n\nNote: {subdomain_request.note}"

    try:
        if requester and requester.email:
            send_makerspace_email(
                makerspace,
                subject,
                body,
                [requester.email],
                stream="account",
                event="subdomain_request_resolved",
                audience="requester",
            )
    except Exception:
        logger.warning(
            "subdomain_request_email_notification_failed",
            extra={"subdomain_request_id": subdomain_request.pk},
            exc_info=True,
        )

    try:
        send_message(makerspace, f"Subdomain request '{label}' was {status}.")
    except Exception:
        logger.warning(
            "subdomain_request_telegram_notification_failed",
            extra={"subdomain_request_id": subdomain_request.pk},
            exc_info=True,
        )
