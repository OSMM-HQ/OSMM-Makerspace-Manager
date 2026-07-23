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
    from apps.encryption.write_fence import assert_mapped_write_allowed

    with transaction.atomic():
        assert_mapped_write_allowed(log.makerspace_id)
        locked = EmailLog.objects.select_for_update().get(pk=log.pk)
        if locked.status == EmailLog.Status.SENDING and not sending_claim_is_stale(locked):
            raise EmailRetryError("This email is still sending; only stalled sends can be retried.")
        if locked.status not in (EmailLog.Status.FAILED, EmailLog.Status.SENDING):
            raise EmailRetryError("Only failed or stalled emails can be retried.")
        if not locked.text_body and not locked.html_body:
            raise EmailRetryError("This email cannot be retried (no stored content).")
        locked.status = EmailLog.Status.PENDING
        locked.error = ""
        locked.save(update_fields=["status", "error", "updated_at"])
        audit.record(
            actor,
            "email.retried",
            makerspace=locked.makerspace,
            target=locked,
            meta={"email_log_id": locked.pk, "event": locked.event, "stream": locked.stream},
        )
        transaction.on_commit(lambda: _enqueue(locked.pk))
        return locked
