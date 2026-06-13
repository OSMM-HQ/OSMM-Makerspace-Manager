import logging

from django.template import Context, Template
from django.utils import timezone

from apps.integrations.email import send_makerspace_email
from apps.integrations.telegram import TelegramDeliveryError, send_message
from apps.hardware_requests.models import HardwareEmailTemplate

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATES = {
    HardwareEmailTemplate.Key.REQUEST_RECEIVED: {
        "subject": "{{ makerspace.name }} request received",
        "text_body": (
            "Your makerspace request #{{ request.id }} was received.\n\n"
            "Status: {{ request.status }}\n"
            "Use your email or phone on the public request page to check status."
        ),
    },
    HardwareEmailTemplate.Key.REQUEST_ACCEPTED: {
        "subject": "{{ makerspace.name }} request approved",
        "text_body": (
            "Your makerspace request #{{ request.id }} has been approved."
            "{% if request.return_due_at %}\n\nReturn by: {{ request.return_due_at }}{% endif %}"
        ),
    },
    HardwareEmailTemplate.Key.REQUEST_REJECTED: {
        "subject": "{{ makerspace.name }} request rejected",
        "text_body": (
            "Your makerspace request #{{ request.id }} was rejected."
            "{% if request.rejection_reason %}\n\nReason: {{ request.rejection_reason }}{% endif %}"
        ),
    },
    HardwareEmailTemplate.Key.REQUEST_ISSUED: {
        "subject": "{{ makerspace.name }} request issued",
        "text_body": (
            "Your approved makerspace request #{{ request.id }} has been handed out."
            "{% if request.return_due_at %}\n\nReturn by: {{ request.return_due_at }}{% endif %}"
        ),
    },
    HardwareEmailTemplate.Key.REQUEST_RETURNED: {
        "subject": "{{ makerspace.name }} request returned",
        "text_body": "Your makerspace request #{{ request.id }} has been returned and closed.",
    },
    HardwareEmailTemplate.Key.RETURN_REMINDER: {
        "subject": "{{ makerspace.name }} return reminder",
        "text_body": (
            "Your makerspace request #{{ request.id }} is due for return."
            "{% if request.return_due_at %}\n\nReturn due: {{ request.return_due_at }}{% endif %}"
        ),
    },
}


def notify_request_submitted(request):
    """Telegram integration point for submitted hardware requests."""
    logger.info(
        "Hardware request submitted.",
        extra={
            "request_id": request.pk,
            "makerspace_id": request.makerspace_id,
            "status": request.status,
        },
    )
    _send_request_message(
        request,
        f"New hardware request #{request.pk} from {request.requester_username}.",
    )
    _send_templated_email(request, HardwareEmailTemplate.Key.REQUEST_RECEIVED)


def notify_request_accepted(request):
    logger.info(
        "Hardware request accepted.",
        extra={
            "request_id": request.pk,
            "makerspace_id": request.makerspace_id,
            "status": request.status,
        },
    )
    _send_templated_email(request, HardwareEmailTemplate.Key.REQUEST_ACCEPTED)


def notify_request_rejected(request):
    logger.info(
        "Hardware request rejected.",
        extra={
            "request_id": request.pk,
            "makerspace_id": request.makerspace_id,
            "status": request.status,
        },
    )
    _send_templated_email(request, HardwareEmailTemplate.Key.REQUEST_REJECTED)


def notify_request_issued(request):
    """Telegram integration point for issued hardware requests."""
    logger.info(
        "Hardware request issued.",
        extra={
            "request_id": request.pk,
            "makerspace_id": request.makerspace_id,
            "status": request.status,
        },
    )
    _send_request_message(request, f"Hardware request #{request.pk} has been issued.")
    _send_templated_email(request, HardwareEmailTemplate.Key.REQUEST_ISSUED)


def notify_request_returned(request):
    """Telegram integration point for returned hardware requests."""
    logger.info(
        "Hardware request returned.",
        extra={
            "request_id": request.pk,
            "makerspace_id": request.makerspace_id,
            "status": request.status,
        },
    )
    _send_request_message(request, f"Hardware request #{request.pk} has been returned.")
    _send_templated_email(request, HardwareEmailTemplate.Key.REQUEST_RETURNED)


def notify_return_due(request):
    logger.info(
        "Hardware request return reminder due.",
        extra={
            "request_id": request.pk,
            "makerspace_id": request.makerspace_id,
            "status": request.status,
        },
    )
    return _send_templated_email(request, HardwareEmailTemplate.Key.RETURN_REMINDER)


def _send_request_message(request, text):
    reply_markup = None
    if request.status == request.Status.PENDING_APPROVAL:
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "Accept", "callback_data": f"accept:{request.pk}"},
                    {
                        "text": "Reject",
                        "callback_data": f"reject:{request.pk}:Rejected from Telegram.",
                    },
                ]
            ]
        }
    try:
        send_message(request.makerspace, text, reply_markup=reply_markup)
    except TelegramDeliveryError:
        logger.exception(
            "Telegram request notification failed.",
            extra={"request_id": request.pk},
        )


def _send_templated_email(request, key):
    recipient = request.requester_contact_email
    if not recipient:
        return False

    rendered = render_email(request, key)
    try:
        sent = send_makerspace_email(
            request.makerspace,
            rendered["subject"],
            rendered["text_body"],
            [recipient],
            html_body=rendered["html_body"],
        )
        return bool(sent)
    except Exception:
        logger.warning(
            "request_status_email_failed",
            extra={"request_id": request.pk, "recipient": recipient, "template": key},
            exc_info=True,
        )
        return False


def render_email(request, key):
    template = HardwareEmailTemplate.objects.filter(
        makerspace=request.makerspace,
        key=key,
        is_active=True,
    ).first()
    defaults = DEFAULT_TEMPLATES[key]
    subject = template.subject if template else defaults["subject"]
    text_body = template.text_body if template else defaults["text_body"]
    html_body = template.html_body if template else defaults.get("html_body", "")
    context = Context(
        {
            "request": request,
            "makerspace": request.makerspace,
            "items": request.items.select_related("product").all(),
            "now": timezone.now(),
        },
        autoescape=True,
    )
    return {
        "subject": Template(subject).render(context).strip(),
        "text_body": Template(text_body).render(context),
        "html_body": Template(html_body).render(context) if html_body else "",
    }
