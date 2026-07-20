import logging

from apps.integrations.email_templates_registry import (
    HARDWARE_REQUESTER_KEYS,
    HARDWARE_STAFF_KEYS,
    PRINTING_REQUESTER_KEYS,
    PRINTING_STAFF_KEYS,
)
from apps.integrations.models import EmailNotificationMute
from apps.makerspaces.models import MakerspaceMembership

logger = logging.getLogger(__name__)

ALWAYS_ON = frozenset({"return_reminder"})


def _mutable_events(keys):
    return tuple(key for key in keys if key not in ALWAYS_ON)


EVENT_CATALOG = {
    ("hardware", "requester"): _mutable_events(HARDWARE_REQUESTER_KEYS),
    ("hardware", "staff"): _mutable_events(HARDWARE_STAFF_KEYS),
    ("printing", "requester"): _mutable_events(PRINTING_REQUESTER_KEYS),
    ("printing", "staff"): _mutable_events(PRINTING_STAFF_KEYS),
}

TARGETS = {
    MakerspaceMembership.Role.SPACE_MANAGER.value: "staff",
    MakerspaceMembership.Role.INVENTORY_MANAGER.value: "staff",
    MakerspaceMembership.Role.MACHINE_MANAGER.value: "staff",
    "requester": "requester",
}

_STREAM_ROLES = {
    "hardware": (
        MakerspaceMembership.Role.SPACE_MANAGER.value,
        MakerspaceMembership.Role.INVENTORY_MANAGER.value,
    ),
    "printing": (
        MakerspaceMembership.Role.SPACE_MANAGER.value,
        MakerspaceMembership.Role.MACHINE_MANAGER.value,
    ),
}


def valid_targets_for_stream(stream):
    roles = _STREAM_ROLES.get(stream)
    if roles is None:
        return ()
    return ("requester", *roles)


def _target_value(target):
    return getattr(target, "value", target)


def is_event_mutable(stream, audience, event) -> bool:
    return event in EVENT_CATALOG.get((stream, audience), ())


def role_muted(makerspace, stream, event, role) -> bool:
    try:
        if not is_event_mutable(stream, "staff", event):
            return False
        return EmailNotificationMute.objects.filter(
            makerspace=makerspace,
            target=_target_value(role),
            stream=stream,
            event=event,
            audience="staff",
        ).exists()
    except Exception:
        logger.warning(
            "email_notification_role_mute_check_failed",
            extra={
                "makerspace_id": getattr(makerspace, "pk", None),
                "stream": stream,
                "event": event,
                "role": role,
            },
            exc_info=True,
        )
        return is_event_mutable(stream, "staff", event)


def is_requester_muted(makerspace, stream, event) -> bool:
    try:
        if not is_event_mutable(stream, "requester", event):
            return False
        return EmailNotificationMute.objects.filter(
            makerspace=makerspace,
            target="requester",
            stream=stream,
            event=event,
            audience="requester",
        ).exists()
    except Exception:
        logger.warning(
            "email_notification_requester_mute_check_failed",
            extra={
                "makerspace_id": getattr(makerspace, "pk", None),
                "stream": stream,
                "event": event,
            },
            exc_info=True,
        )
        return is_event_mutable(stream, "requester", event)


def muted_targets(makerspace, stream, event) -> set[str]:
    try:
        audiences = [
            audience
            for audience in ("requester", "staff")
            if is_event_mutable(stream, audience, event)
        ]
        if not audiences:
            return set()
        valid_targets = valid_targets_for_stream(stream)
        return set(
            EmailNotificationMute.objects.filter(
                makerspace=makerspace,
                stream=stream,
                event=event,
                audience__in=audiences,
                target__in=valid_targets,
            ).values_list("target", flat=True)
        )
    except Exception:
        logger.warning(
            "email_notification_muted_targets_check_failed",
            extra={
                "makerspace_id": getattr(makerspace, "pk", None),
                "stream": stream,
                "event": event,
            },
            exc_info=True,
        )
        return _fail_closed_targets(stream, event)


def _fail_closed_targets(stream, event) -> set[str]:
    targets = set()
    if is_event_mutable(stream, "requester", event):
        targets.add("requester")
    if is_event_mutable(stream, "staff", event):
        targets.update(valid_targets_for_stream(stream)[1:])
    return targets


