import random

from celery import shared_task
from django.db import transaction

from apps.integrations.dispatch import _deliver
from apps.integrations.models import EmailLog
from apps.integrations.smtp_validation import (
    email_task_hard_limit,
    email_task_soft_limit,
    sending_claim_is_stale,
)

@shared_task(
    bind=True,
    max_retries=3,
    soft_time_limit=email_task_soft_limit(),
    time_limit=email_task_hard_limit(),
)
def deliver_email_task(self, log_id):
    log = _claim_log(log_id)
    if log is None:
        return
    _deliver(log)
    log.refresh_from_db()
    if log.status == EmailLog.Status.FAILED:
        try:
            raise self.retry(countdown=_retry_countdown(self.request.retries))
        except self.MaxRetriesExceededError:
            return

def _retry_countdown(retries):
    # Celery remains at-least-once: a worker crash after SMTP accepts the message but
    # before SENT is committed can still resend. The SENDING claim narrows duplicate
    # delivery and stale claims are reclaimed after the hard task limit.
    base = min(60 * (2**retries), 15 * 60)
    return base + random.randint(0, min(base, 30))

def _claim_log(log_id):
    with transaction.atomic():
        log = EmailLog.objects.select_for_update().filter(pk=log_id).first()
        if log is None or log.status == EmailLog.Status.SENT:
            return None
        if log.status == EmailLog.Status.SENDING and not sending_claim_is_stale(log):
            return None
        log.status = EmailLog.Status.SENDING
        log.error = ""
        log.save(update_fields=["status", "error", "updated_at"])
        return log
