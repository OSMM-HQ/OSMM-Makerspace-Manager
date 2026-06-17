import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection

logger = logging.getLogger(__name__)


def makerspace_mail_connection(makerspace):
    if not makerspace.smtp_host:
        return None, settings.DEFAULT_FROM_EMAIL
    # use_ssl (implicit SSL, port 465) and use_tls (STARTTLS, port 587) are
    # mutually exclusive in Django's SMTP backend — prefer SSL when both are set.
    use_ssl = makerspace.smtp_use_ssl
    use_tls = makerspace.smtp_use_tls and not use_ssl
    return (
        get_connection(
            host=makerspace.smtp_host,
            port=makerspace.smtp_port,
            username=makerspace.smtp_username or None,
            password=makerspace.get_smtp_password() or None,
            use_tls=use_tls,
            use_ssl=use_ssl,
        ),
        makerspace.smtp_from_email or settings.DEFAULT_FROM_EMAIL,
    )


def platform_mail_connection():
    """Connection + from-email for INSTANCE-WIDE auth mail (password resets).

    Uses the superadmin-configured PlatformEmailSettings when a host is set; otherwise
    returns (None, settings.DEFAULT_FROM_EMAIL) so Django's default EMAIL_BACKEND is used.
    NEVER uses per-makerspace SMTP. If a platform host IS configured but broken, do NOT
    silently fall back -- return its connection and let the caller's fail-safe handle errors.
    """
    from apps.integrations.models import PlatformEmailSettings

    cfg = PlatformEmailSettings.load()
    smtp_host = (cfg.smtp_host or "").strip()
    if not smtp_host:
        return None, settings.DEFAULT_FROM_EMAIL
    use_ssl = cfg.smtp_use_ssl
    use_tls = cfg.smtp_use_tls and not use_ssl
    return (
        get_connection(
            host=smtp_host,
            port=cfg.smtp_port,
            username=cfg.smtp_username or None,
            password=cfg.get_smtp_password() or None,
            use_tls=use_tls,
            use_ssl=use_ssl,
        ),
        cfg.from_email or settings.DEFAULT_FROM_EMAIL,
    )


def platform_email_configured() -> bool:
    from apps.integrations.models import PlatformEmailSettings

    cfg = PlatformEmailSettings.load()
    return bool((cfg.smtp_host or "").strip())


def send_password_reset_email(recipient, reset_url):
    connection, from_email = platform_mail_connection()
    subject = "Reset your password"
    body = (
        "We received a request to reset your password.\n\n"
        f"Reset it here:\n{reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )
    msg = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=from_email,
        to=[recipient],
        connection=connection,
    )
    return msg.send()


def send_makerspace_email(makerspace, subject, body, recipients, html_body=None):
    recipients = [recipient for recipient in recipients if recipient]
    if not recipients:
        return 0

    connection, from_email = makerspace_mail_connection(makerspace)
    message = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=from_email,
        to=recipients,
        connection=connection,
    )
    if html_body:
        message.attach_alternative(html_body, "text/html")
    return message.send()
