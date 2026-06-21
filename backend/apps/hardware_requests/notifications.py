import logging

from apps.integrations.email_templates import hardware_context, render
from apps.integrations.email import send_makerspace_email
from apps.integrations.telegram import TelegramDeliveryError, send_message
from apps.hardware_requests.staff_notifications import send_staff_hardware_email

logger = logging.getLogger(__name__)

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
        _build_submitted_request_message(request),
    )
    _send_templated_email(request, "request_received")
    _send_staff_email(request, "submitted")


def notify_request_accepted(request):
    logger.info(
        "Hardware request accepted.",
        extra={
            "request_id": request.pk,
            "makerspace_id": request.makerspace_id,
            "status": request.status,
        },
    )
    _send_templated_email(request, "request_accepted")
    _send_staff_email(request, "accepted")


def notify_request_rejected(request):
    logger.info(
        "Hardware request rejected.",
        extra={
            "request_id": request.pk,
            "makerspace_id": request.makerspace_id,
            "status": request.status,
        },
    )
    _send_templated_email(request, "request_rejected")
    _send_staff_email(request, "rejected")


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
    _send_templated_email(request, "request_issued")
    _send_staff_email(request, "issued")


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
    _send_templated_email(request, "request_returned")
    _send_staff_email(request, request.status)


def notify_return_due(request):
    logger.info(
        "Hardware request return reminder due.",
        extra={
            "request_id": request.pk,
            "makerspace_id": request.makerspace_id,
            "status": request.status,
        },
    )
    sent = _send_templated_email(request, "return_reminder", sync=True)
    staff_sent = _send_staff_email(request, "return_reminder", sync=True)
    # Mark the reminder cycle complete if the borrower OR staff was actually reminded.
    # Returning the borrower-only result would leave return_reminder_sent_at null whenever
    # the borrower has no reachable email (blank contact / persistent bounce), so the cron
    # would re-send the staff reminder every run. A transient SMTP outage hits both sends
    # (shared makerspace connection) → both False → still retried next run, as intended.
    return bool(sent) or bool(staff_sent)


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


def _build_submitted_request_message(request):
    lines = [
        f"New hardware request #{request.pk}",
        f"Requester: {request.requester_username or 'Unknown requester'}",
    ]
    if request.requester_contact_email:
        lines.append(f"Email: {request.requester_contact_email}")
    if request.requester_contact_phone:
        lines.append(f"Phone: {request.requester_contact_phone}")
    if request.requested_for:
        # requested_for is an uncapped TextField; clamp it so one long value can't
        # push the payload past Telegram's 4096-char limit (a failed send would be
        # swallowed by _send_request_message, dropping the alert + approve buttons).
        lines.append(f"Requested for: {_clamp(request.requested_for, 300)}")

    items = list(request.items.select_related("product"))
    if items:
        lines.append("Items:")
        shown = items[:40]
        for item in shown:
            lines.append(f"- {_clamp(item.product.name, 80)}: {item.requested_quantity}")
        if len(items) > len(shown):
            lines.append(f"- ...and {len(items) - len(shown)} more")
    else:
        lines.append("Items: None")
    # Final safety net: stay under Telegram's hard 4096-char text limit.
    return _clamp("\n".join(lines), 4000)


def _clamp(text, limit):
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _send_templated_email(request, key, *, sync=False):
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
            stream="hardware",
            event=key,
            audience="requester",
            sync=sync,
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
    return render(
        request.makerspace,
        "hardware",
        "requester",
        key,
        hardware_context(request, staff=False),
    )


def _send_staff_email(request, event, *, sync=False) -> bool:
    return send_staff_hardware_email(request, event, sync=sync)
