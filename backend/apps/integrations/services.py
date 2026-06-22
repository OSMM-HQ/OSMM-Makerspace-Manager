from django.db import transaction

from apps.audit import services as audit
from apps.integrations.dispatch import _enqueue
from apps.integrations.models import EmailLog


class EmailRetryError(Exception):
    pass


def retry_email_log(actor, log):
    if log.status != EmailLog.Status.FAILED:
        raise EmailRetryError("Only failed emails can be retried.")
    if not log.text_body and not log.html_body:
        raise EmailRetryError("This email cannot be retried (no stored content).")

    log.status = EmailLog.Status.PENDING
    log.error = ""
    log.save(update_fields=["status", "error", "updated_at"])
    audit.record(
        actor,
        "email.retried",
        makerspace=log.makerspace,
        target=log,
        meta={"to_email": log.to_email, "event": log.event, "stream": log.stream},
    )
    transaction.on_commit(lambda: _enqueue(log.pk))
    return log
