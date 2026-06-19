import logging

from apps.accounts.models import User
from apps.makerspaces.models import MakerspaceMembership

logger = logging.getLogger(__name__)


_STREAM_ROLES = {
    "hardware": (
        MakerspaceMembership.Role.SPACE_MANAGER,
        MakerspaceMembership.Role.INVENTORY_MANAGER,
    ),
    "printing": (
        MakerspaceMembership.Role.SPACE_MANAGER,
        MakerspaceMembership.Role.PRINT_MANAGER,
    ),
}


def staff_emails_for_stream(makerspace, stream) -> list[str]:
    try:
        if not getattr(makerspace, "staff_notifications_enabled", True):
            return []

        roles = _STREAM_ROLES.get(stream)
        if roles is None:
            logger.warning(
                "staff_notification_unknown_stream",
                extra={
                    "makerspace_id": getattr(makerspace, "pk", None),
                    "stream": stream,
                },
            )
            return []

        memberships = (
            MakerspaceMembership.objects.filter(
                makerspace=makerspace,
                role__in=roles,
                receives_notifications=True,
                user__is_active=True,
                user__access_status=User.AccessStatus.ACTIVE,
            )
            .exclude(user__is_superuser=True)
            .exclude(user__role=User.Role.SUPERADMIN)
            .select_related("user")
            .order_by("id")
        )
        seen = set()
        recipients = []
        for membership in memberships:
            email = (membership.user.email or "").strip()
            if not email:
                continue
            normalized = email.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            recipients.append(email)
        return recipients
    except Exception:
        logger.warning(
            "staff_notification_recipient_resolution_failed",
            extra={
                "makerspace_id": getattr(makerspace, "pk", None),
                "stream": stream,
            },
            exc_info=True,
        )
        return []
