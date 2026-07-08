import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def emit_notification(makerspace, *, title, level="info", event="", body="", url_path=""):
    """Fail-safe emit of a staff Notification row.

    A notification write must NEVER break the underlying workflow/dispatch, so
    the whole body is guarded and the actual create is deferred to
    ``transaction.on_commit`` (a rolled-back workflow leaves no notification; when
    no transaction is open the callback runs immediately). No-ops when the
    makerspace has not opted into the ``notifications`` module.
    """
    try:
        if makerspace is None:
            return
        from apps.makerspaces.platform import module_enabled

        if not module_enabled(makerspace, "notifications"):
            return
        makerspace_id = makerspace.pk
        payload = {
            "level": level,
            "event": event,
            "title": (title or "")[:200],
            "body": body or "",
            "url_path": (url_path or "")[:300],
        }

        def _create():
            try:
                from apps.notifications.models import Notification

                Notification.objects.create(makerspace_id=makerspace_id, **payload)
            except Exception:
                logger.exception(
                    "notification_emit_create_failed",
                    extra={"makerspace_id": makerspace_id, "event": event},
                )

        transaction.on_commit(_create)
    except Exception:
        logger.exception("notification_emit_failed", extra={"event": event})
