import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.admin_api import bulk_import
from apps.admin_api.models import BulkImportJob

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0)
def process_bulk_import_job(self, job_id):
    job = _claim_job(job_id)
    if job is None:
        return
    try:
        rows = _job_rows(job)
        BulkImportJob.objects.filter(pk=job.pk).update(
            total_rows=len(rows),
            processed_rows=0,
        )
        progress = _progress_updater(job.pk)
        if job.mode == BulkImportJob.Mode.APPLY:
            result = bulk_import.apply_import(
                job.actor,
                job.makerspace,
                rows,
                job.mapping,
                progress_callback=progress,
            )
        else:
            result = bulk_import.preview_import(
                job.makerspace,
                rows,
                job.mapping,
                progress_callback=progress,
            )
        _complete_job(job.pk, result, len(rows))
    except Exception as exc:  # worker boundary: capture bad files and unexpected failures.
        logger.exception("Bulk import job %s failed.", job_id)
        BulkImportJob.objects.filter(pk=job.pk).update(
            status=BulkImportJob.Status.FAILED,
            error=str(exc) or exc.__class__.__name__,
            completed_at=timezone.now(),
        )


def _claim_job(job_id):
    with transaction.atomic():
        job = (
            BulkImportJob.objects.select_for_update()
            .select_related("makerspace", "actor")
            .filter(pk=job_id)
            .first()
        )
        if job is None or job.status != BulkImportJob.Status.PENDING:
            return None
        job.status = BulkImportJob.Status.RUNNING
        job.error = ""
        job.save(update_fields=["status", "error", "updated_at"])
        return job


def _job_rows(job):
    if job.rows:
        return job.rows
    if not job.upload:
        raise ValueError("Bulk import job has no file or rows.")
    with job.upload.open("rb"):
        return bulk_import.rows_from_upload(job.upload)


def _progress_updater(job_id):
    last_saved = {"value": 0}

    def update(processed, total):
        if processed != total and processed - last_saved["value"] < 100:
            return
        last_saved["value"] = processed
        BulkImportJob.objects.filter(pk=job_id).update(processed_rows=processed)

    return update


def _complete_job(job_id, result, total_rows):
    summary = result.get("summary") or {}
    BulkImportJob.objects.filter(pk=job_id).update(
        status=BulkImportJob.Status.COMPLETED,
        result=result,
        total_rows=total_rows,
        processed_rows=total_rows,
        created_count=result.get("created") or summary.get("create") or 0,
        updated_count=result.get("updated") or summary.get("update") or 0,
        error_count=summary.get("errors") or len(result.get("errors") or []),
        warning_count=summary.get("warnings") or len(result.get("warnings") or []),
        completed_at=timezone.now(),
    )
