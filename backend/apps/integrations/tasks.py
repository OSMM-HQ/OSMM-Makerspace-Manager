from celery import shared_task
from django.db import transaction

from apps.integrations.dispatch import _deliver
from apps.integrations.models import EmailLog


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def deliver_email_task(self, log_id):
    with transaction.atomic():
        log = EmailLog.objects.select_for_update().filter(pk=log_id).first()
        if log is None or log.status == EmailLog.Status.SENT:
            return
        _deliver(log)
    log.refresh_from_db()
    if log.status == EmailLog.Status.FAILED:
        try:
            raise self.retry(countdown=60)
        except self.MaxRetriesExceededError:
            return
