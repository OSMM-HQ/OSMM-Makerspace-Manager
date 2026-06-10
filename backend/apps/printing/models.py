from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class PrintBucket(models.Model):
    makerspace = models.ForeignKey(
        "makerspaces.Makerspace",
        on_delete=models.CASCADE,
        related_name="print_buckets",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["makerspace", "name"],
                name="uniq_print_bucket_makerspace_name",
            ),
        ]
        ordering = ["makerspace__name", "name"]

    def __str__(self):
        return f"{self.makerspace}: {self.name}"


class PrintRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        PRINTING = "printing", "Printing"
        COMPLETED = "completed", "Completed"
        REJECTED = "rejected", "Rejected"
        FAILED = "failed", "Failed"

    bucket = models.ForeignKey(
        PrintBucket,
        on_delete=models.PROTECT,
        related_name="print_requests",
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="print_requests",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    material = models.CharField(max_length=100, blank=True)
    color = models.CharField(max_length=100, blank=True)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    source_link = models.URLField(blank=True)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    reason = models.TextField(blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="handled_print_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def makerspace(self):
        return self.bucket.makerspace

    @property
    def makerspace_id(self):
        return self.bucket.makerspace_id

    def __str__(self):
        return f"{self.title} ({self.status})"
