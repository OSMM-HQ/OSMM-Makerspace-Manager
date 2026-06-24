from django.conf import settings
from django.db import models


class BulkImportJob(models.Model):
    class Mode(models.TextChoices):
        PREVIEW = "preview", "Preview"
        APPLY = "apply", "Apply"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    makerspace = models.ForeignKey(
        "makerspaces.Makerspace",
        on_delete=models.CASCADE,
        related_name="bulk_import_jobs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bulk_import_jobs",
    )
    mode = models.CharField(max_length=20, choices=Mode.choices)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    upload = models.FileField(upload_to="bulk-imports/%Y/%m/%d/", blank=True)
    rows = models.JSONField(default=list, blank=True)
    mapping = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    total_rows = models.PositiveIntegerField(default=0)
    processed_rows = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["makerspace", "status", "created_at"]),
        ]

    def __str__(self):
        return f"Bulk import {self.id} [{self.status}]"
