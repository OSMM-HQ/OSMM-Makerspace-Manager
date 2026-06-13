import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection

logger = logging.getLogger(__name__)


def makerspace_mail_connection(makerspace):
    if not makerspace.smtp_host:
        return None, settings.DEFAULT_FROM_EMAIL
    return (
        get_connection(
            host=makerspace.smtp_host,
            port=makerspace.smtp_port,
            username=makerspace.smtp_username or None,
            password=makerspace.get_smtp_password() or None,
            use_tls=makerspace.smtp_use_tls,
        ),
        makerspace.smtp_from_email or settings.DEFAULT_FROM_EMAIL,
    )


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
