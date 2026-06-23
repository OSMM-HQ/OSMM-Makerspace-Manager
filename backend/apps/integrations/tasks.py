from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.integrations.dispatch import _deliver
from apps.integrations.models import EmailLog
from apps.integrations.smtp_validation import email_task_hard_limit, email_task_soft_limit


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
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
            raise self.retry(countdown=60)
        except self.MaxRetriesExceededError:
            return


def _claim_log(log_id):
    with transaction.atomic():
        log = EmailLog.objects.select_for_update().filter(pk=log_id).first()
        if log is None or log.status == EmailLog.Status.SENT:
            return None
        if log.status == EmailLog.Status.SENDING and not _sending_claim_is_stale(log):
            return None
        log.status = EmailLog.Status.SENDING
        log.error = ""
        log.save(update_fields=["status", "error", "updated_at"])
        return log


def _sending_claim_is_stale(log) -> bool:
    stale_after = timezone.now() - timedelta(seconds=email_task_hard_limit() + 5)
    return log.updated_at <= stale_after
