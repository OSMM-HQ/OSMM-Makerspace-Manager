import logging

from apps.hardware_requests.models import HardwareRequest
from apps.integrations.email import send_makerspace_email
from apps.integrations.email_templates import hardware_context, render
from apps.integrations.staff_notifications import staff_emails_for_stream

logger = logging.getLogger(__name__)

def send_staff_hardware_email(request, event, *, sync=False) -> bool:
    """Send the staff-facing hardware notification. Returns True iff at least one staff
    email was actually delivered (used by notify_return_due to avoid re-sending the staff
    reminder on every cron run when the borrower has no reachable email)."""
    try:
        staff_request = (
            HardwareRequest.objects.select_related(
                "makerspace",
                "requester",
                "assigned_box",
            )
            .prefetch_related("items__product")
            .get(pk=request.pk)
        )
        recipients = staff_emails_for_stream(staff_request.makerspace, "hardware")
        if not recipients:
            return False

        rendered = render(
            staff_request.makerspace,
            "hardware",
            "staff",
            event,
            hardware_context(staff_request, staff=True),
        )
        return bool(
            send_makerspace_email(
                staff_request.makerspace,
                rendered["subject"],
                rendered["text_body"],
                recipients,
                html_body=rendered["html_body"],
                stream="hardware",
                event=event,
                audience="staff",
                sync=sync,
            )
        )
    except Exception:
        logger.warning(
            "hardware_staff_notification_failed",
            extra={
                "request_id": getattr(request, "pk", None),
                "event": event,
            },
            exc_info=True,
        )
        return False


def _staff_summary(request):
    lines = [
        f"Status: {request.status}",
        f"Requester: {request.requester_username or 'Unknown requester'}",
    ]
    if request.requester_contact_email:
        lines.append(f"Email: {request.requester_contact_email}")
    if request.requester_contact_phone:
        lines.append(f"Phone: {request.requester_contact_phone}")
    if request.assigned_box_id:
        lines.append(f"Box: {request.assigned_box.code}")
    if request.return_due_at:
        lines.append(f"Return due: {request.return_due_at}")
    if request.rejection_reason:
        lines.append(f"Reason: {request.rejection_reason}")
    return "\n".join(lines)
