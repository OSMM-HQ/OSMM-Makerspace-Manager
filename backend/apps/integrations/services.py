from django.db import transaction

from apps.audit import services as audit
from apps.integrations.dispatch import _enqueue
from apps.integrations.models import EmailLog
from apps.integrations.smtp_validation import sending_claim_is_stale


class EmailRetryError(Exception):
    pass


def retry_email_log(actor, log):
    # Failed sends are always retriable. A SENDING row is normally an in-flight claim
    # (must NOT be retried — that would double-deliver), but a STALE claim means the
    # worker died after claiming and before committing the result, leaving it stuck
    # forever — surface that in the Retry path so it stays recoverable without a DB fix.
    if log.status == EmailLog.Status.SENDING and not sending_claim_is_stale(log):
        raise EmailRetryError("This email is still sending; only stalled sends can be retried.")
    if log.status not in (EmailLog.Status.FAILED, EmailLog.Status.SENDING):
        raise EmailRetryError("Only failed or stalled emails can be retried.")
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
