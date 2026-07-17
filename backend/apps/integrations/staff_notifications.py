import logging

from apps.accounts.models import User
from apps.integrations import notification_rules
from apps.makerspaces.models import MakerspaceMembership

logger = logging.getLogger(__name__)


_FEATURE_ROLES = {
    "hardware_requests": (
        MakerspaceMembership.Role.SPACE_MANAGER,
        MakerspaceMembership.Role.INVENTORY_MANAGER,
    ),
    "printing": (
        MakerspaceMembership.Role.SPACE_MANAGER,
        MakerspaceMembership.Role.PRINT_MANAGER,
    ),
    "events": (MakerspaceMembership.Role.SPACE_MANAGER,),
    "bookings": (MakerspaceMembership.Role.SPACE_MANAGER,),
    "maintenance": (
        MakerspaceMembership.Role.SPACE_MANAGER,
        MakerspaceMembership.Role.MACHINE_MANAGER,
    ),
}

_FEATURE_STREAMS = {
    "hardware_requests": "hardware",
    "printing": "printing",
}
_STREAM_FEATURES = {value: key for key, value in _FEATURE_STREAMS.items()}


def staff_emails_for_feature(makerspace, feature, event=None) -> list[str]:
    try:
        if not getattr(makerspace, "staff_notifications_enabled", True):
            return []

        roles = _FEATURE_ROLES.get(feature)
        if roles is None:
            logger.warning(
                "staff_notification_unknown_feature",
                extra={
                    "makerspace_id": getattr(makerspace, "pk", None),
                    "feature": feature,
                },
            )
            return []

        muted_roles = set()
        stream = _FEATURE_STREAMS.get(feature)
        if stream and event and notification_rules.is_event_mutable(stream, "staff", event):
            muted_roles = {
                role
                for role in roles
                if notification_rules.role_muted(makerspace, stream, event, role)
            }

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
        if muted_roles:
            memberships = memberships.exclude(role__in=muted_roles)

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
                "feature": feature,
            },
            exc_info=True,
        )
        return []


def staff_emails_for_stream(makerspace, stream, event=None) -> list[str]:
    feature = _STREAM_FEATURES.get(stream)
    if feature is None:
        logger.warning(
            "staff_notification_unknown_stream",
            extra={
                "makerspace_id": getattr(makerspace, "pk", None),
                "stream": stream,
            },
        )
        return []
    return staff_emails_for_feature(makerspace, feature, event=event)
