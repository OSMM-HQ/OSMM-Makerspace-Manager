import logging

from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone

from apps.integrations.models import EmailLog

logger = logging.getLogger(__name__)


def dispatch_email(
    *,
    to_email,
    subject,
    text_body,
    html_body="",
    makerspace=None,
    stream="",
    event="",
    audience="",
    connection="makerspace",
    persist_body=True,
    sync=False,
):
    # persist_body=False keeps the rendered body OUT of the stored row (e.g. password
    # reset emails embed a live recovery token in the body — persisting it would leave a
    # usable token in the DB + Django admin until expiry). We still deliver the real body:
    # it's set on the in-memory instance below and _deliver never re-saves the body fields.
    log = EmailLog.objects.create(
        makerspace=makerspace,
        to_email=to_email,
        subject=subject,
        text_body=text_body if persist_body else "",
        html_body=html_body if persist_body else "",
        stream=stream,
        event=event,
        audience=audience,
        connection_kind=connection,
    )
    if not persist_body:
        # In-memory only — _deliver's save(update_fields=...) excludes the body fields,
        # so the stored row stays redacted while delivery uses the real content.
        log.text_body = text_body
        log.html_body = html_body
    if sync:
        return _deliver(log)
    transaction.on_commit(lambda lid=log.id: _enqueue(lid))
    return log


def _enqueue(log_id):
    from apps.integrations.tasks import deliver_email_task

    try:
        deliver_email_task.delay(log_id)
    except Exception as exc:
        EmailLog.objects.filter(pk=log_id).update(
            status=EmailLog.Status.FAILED,
            error=("enqueue failed: " + str(exc))[:2000],
        )
        logger.exception("email_enqueue_failed", extra={"email_log_id": log_id})


def _deliver(log):
    if log.status == EmailLog.Status.SENT:
        return log

    try:
        from apps.integrations.email import (
            makerspace_mail_connection,
            platform_mail_connection,
        )

        if log.connection_kind == "makerspace" and log.makerspace_id:
            connection, from_email = makerspace_mail_connection(log.makerspace)
        else:
            connection, from_email = platform_mail_connection()
        msg = EmailMultiAlternatives(
            subject=log.subject,
            body=log.text_body,
            from_email=from_email,
            to=[log.to_email],
            connection=connection,
        )
        if log.html_body:
            msg.attach_alternative(log.html_body, "text/html")
        msg.send()
    except Exception as exc:
        log.status = EmailLog.Status.FAILED
        log.error = str(exc)[:2000]
        logger.exception(
            "email_delivery_failed",
            extra={"email_log_id": log.pk, "to_email": log.to_email},
        )
    else:
        log.status = EmailLog.Status.SENT
        log.error = ""
        log.sent_at = timezone.now()
    finally:
        log.attempts += 1
        log.save(
            update_fields=[
                "status",
                "error",
                "attempts",
                "sent_at",
                "updated_at",
            ]
        )
    return log
