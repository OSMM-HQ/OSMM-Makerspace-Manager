"""Fail-safe notification seam for machine-service lifecycle events."""

import logging

from apps.notifications.emit import emit_notification

logger = logging.getLogger(__name__)


def notify_service_status(service_request, event):
    """Emit a staff notification without allowing delivery to break the workflow."""
    try:
        makerspace = service_request.bucket.machine.makerspace
        emit_notification(
            makerspace,
            event=f"machine_service.{event}",
            title="Machine service request updated",
            body=(
                f"Machine service request #{service_request.pk} {event}. "
                f"Status: {service_request.status}."
            ),
            url_path=f"/admin/machine-service/requests/{service_request.pk}",
        )
    except Exception:
        logger.exception(
            "machine_service_notification_failed",
            extra={"request_id": getattr(service_request, "pk", None), "event": event},
        )
