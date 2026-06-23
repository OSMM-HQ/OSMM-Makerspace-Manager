import ipaddress
import socket
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

ALLOWED_SMTP_PORTS = {25, 465, 587, 2525}
DEFAULT_SMTP_TIMEOUT_SECONDS = 10
DEFAULT_EMAIL_TASK_SOFT_SECONDS = 15
DEFAULT_EMAIL_TASK_HARD_SECONDS = 20
SENDING_CLAIM_STALE_BUFFER_SECONDS = 5


def smtp_timeout_seconds() -> int:
    return int(getattr(settings, "EMAIL_SMTP_TIMEOUT", DEFAULT_SMTP_TIMEOUT_SECONDS))


def email_task_soft_limit() -> int:
    return int(
        getattr(settings, "EMAIL_TASK_SOFT_TIME_LIMIT", DEFAULT_EMAIL_TASK_SOFT_SECONDS)
    )


def email_task_hard_limit() -> int:
    return int(
        getattr(settings, "EMAIL_TASK_HARD_TIME_LIMIT", DEFAULT_EMAIL_TASK_HARD_SECONDS)
    )


def sending_claim_is_stale(log) -> bool:
    """A ``SENDING`` EmailLog whose claim predates the hard task limit is stuck — the
    worker crashed/was killed after claiming the row but before committing SENT/FAILED
    (Celery acks early), so no retry will re-fire. Such a row is safe to reclaim."""
    stale_after = timezone.now() - timedelta(
        seconds=email_task_hard_limit() + SENDING_CLAIM_STALE_BUFFER_SECONDS
    )
    return log.updated_at <= stale_after



def validate_smtp_settings(attrs, instance=None):
    host = attrs.get("smtp_host")
    port = attrs.get("smtp_port")
    if host is None and instance is not None:
        host = instance.smtp_host
    if port is None and instance is not None:
        port = instance.smtp_port
    validate_smtp_endpoint(host, port)


def validate_smtp_endpoint(host, port):
    host = (host or "").strip()
    if not host:
        return
    try:
        port = int(port)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"smtp_port": "Enter a valid SMTP port."}) from exc
    if port < 1 or port > 65535:
        raise ValidationError({"smtp_port": "Enter a valid SMTP port."})
    if port not in ALLOWED_SMTP_PORTS and not _private_smtp_allowed():
        raise ValidationError(
            {"smtp_port": "SMTP port must be one of 25, 465, 587, or 2525."}
        )
    if _has_invalid_host_syntax(host):
        raise ValidationError({"smtp_host": "Enter a bare SMTP hostname."})
    literal = _ip_literal(host)
    if literal is not None:
        if _private_smtp_allowed() and _is_dev_address(literal):
            return
        raise ValidationError({"smtp_host": "SMTP host must be a public DNS hostname."})

    resolved = _resolve_host(host, port)
    for address in resolved:
        if _address_is_blocked(address):
            if _private_smtp_allowed() and _is_dev_address(address):
                continue
            raise ValidationError({"smtp_host": "SMTP host resolves to a blocked address."})


def sanitize_email_error(exc) -> str:
    name = exc.__class__.__name__ if exc else "UnknownError"
    safe_name = "".join(ch for ch in name if ch.isalnum() or ch == "_") or "UnknownError"
    return f"email_delivery_failed:{safe_name}"[:2000]


def _has_invalid_host_syntax(host: str) -> bool:
    if any(ch.isspace() for ch in host):
        return True
    return any(token in host for token in (":", "/", "\\", "@"))


def _ip_literal(host: str):
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None


def _resolve_host(host: str, port: int):
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValidationError({"smtp_host": "SMTP host could not be resolved."}) from exc
    addresses = {ipaddress.ip_address(record[4][0]) for record in records}
    if not addresses:
        raise ValidationError({"smtp_host": "SMTP host could not be resolved."})
    return addresses


def _private_smtp_allowed() -> bool:
    return bool(settings.DEBUG and getattr(settings, "ALLOW_PRIVATE_SMTP_HOSTS", False))


def _is_dev_address(address) -> bool:
    return address.is_loopback or address.is_private


def _address_is_blocked(address) -> bool:
    return (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


