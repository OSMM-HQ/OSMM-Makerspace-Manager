"""Foundation models for the per-machine service-request queue."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import IntegrityError, models, transaction
from django.db.models import Q

from apps.encryption.mappers import ScopedPiiModelMixin, ScopedPiiQuerySet

class ServiceBucket(models.Model):
    machine = models.ForeignKey(
        "machines.Machine", on_delete=models.PROTECT, related_name="service_buckets"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["machine", "name"], name="uniq_service_bucket_machine_name"
            )
        ]
        indexes = [models.Index(fields=["machine", "is_active"], name="service_bucket_machine_active_idx")]
        ordering = ["machine__name", "name"]

    def __str__(self):
        return f"{self.machine}: {self.name}"


def get_or_create_default_bucket(machine, *, makerspace=None):
    """Return the locked machine's active default service bucket.

    A service queue is only meaningful on an active, currently-idle machine.  The
    machine row lock serializes competing initializers; the IntegrityError branch
    also covers deployments where a concurrent transaction won before our lock.
    """
    from apps.machines.models import Machine

    if not getattr(machine, "pk", None):
        raise ValidationError("Machine must be saved before creating a service bucket.")
    with transaction.atomic():
        locked = Machine.objects.select_for_update().get(pk=machine.pk)
        expected_makerspace_id = getattr(makerspace, "pk", makerspace)
        if (
            not locked.makerspace_id
            or not locked.is_active
            or locked.status != Machine.Status.IDLE
            or (expected_makerspace_id is not None and locked.makerspace_id != expected_makerspace_id)
        ):
            raise ValidationError("Only an active idle machine can receive service requests.")
        try:
            bucket, _ = ServiceBucket.objects.get_or_create(
                machine=locked,
                name="Service Requests",
                defaults={"is_active": True},
            )
        except IntegrityError:
            bucket = ServiceBucket.objects.get(machine=locked, name="Service Requests")
        if not bucket.is_active:
            bucket.is_active = True
            bucket.save(update_fields=["is_active", "updated_at"])
        return bucket


class MachineServiceRequest(ScopedPiiModelMixin, models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        COLLECTED = "collected", "Collected"
        REJECTED = "rejected", "Rejected"
        FAILED = "failed", "Failed"

    bucket = models.ForeignKey(ServiceBucket, on_delete=models.PROTECT, related_name="service_requests")
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="machine_service_requests")
    # Member ownership was introduced after staff-originated requests already
    # existed.  Keep those historical rows intact; member surfaces must use this
    # field rather than the legacy requester relation.
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="member_machine_service_requests",
    )
    requester_name = models.TextField(blank=True)
    contact_email = models.TextField(blank=True)
    contact_phone = models.TextField(blank=True)
    public_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    source_link = models.URLField(blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING, db_index=True)
    reason = models.TextField(blank=True)
    assigned_machine = models.ForeignKey(
        "machines.Machine", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="assigned_service_requests",
    )
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="handled_service_requests")
    accepted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="accepted_service_requests")
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    collected_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="collected_service_requests")
    collected_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    estimated_minutes = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    actual_minutes = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    fail_percent_complete = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class ServiceRequestQuerySet(ScopedPiiQuerySet):
        def update(self, **kwargs):
            if "status" in kwargs:
                raise RuntimeError("MachineServiceRequest status is workflow-managed.")
            return super().update(**kwargs)

    objects = ServiceRequestQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["requester", "-created_at"], name="servicereq_requester_created_idx"),
            models.Index(fields=["member", "-created_at"], name="servicereq_member_created_idx"),
            models.Index(fields=["bucket", "status", "-created_at"], name="servicereq_bucket_status_idx"),
            models.Index(fields=["assigned_machine", "status", "-created_at"], name="servicereq_machine_status_idx"),
            models.Index(fields=["completed_at"], name="servicereq_completed_idx"),
            models.Index(fields=["failed_at"], name="servicereq_failed_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(estimated_minutes__gte=0), name="service_req_est_minutes_nonnegative"),
            models.CheckConstraint(condition=Q(actual_minutes__gte=0), name="service_req_actual_minutes_nonnegative"),
            models.CheckConstraint(condition=Q(fail_percent_complete__gte=0, fail_percent_complete__lte=100), name="service_req_fail_percent_range"),
        ]
        ordering = ["-created_at"]

    @property
    def makerspace(self):
        return self.bucket.machine.makerspace

    @property
    def makerspace_id(self):
        return self.bucket.machine.makerspace_id

    def save(self, *args, **kwargs):
        if self._state.adding and self.assigned_machine_id is None and self.bucket_id:
            self.assigned_machine_id = self.bucket.machine_id
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.status})"


class ServiceRequestFile(models.Model):
    class Kind(models.TextChoices):
        ATTACHMENT = "attachment", "Attachment"

    service_request = models.ForeignKey(
        MachineServiceRequest, null=True, blank=True, on_delete=models.CASCADE, related_name="files"
    )
    machine = models.ForeignKey("machines.Machine", on_delete=models.PROTECT, related_name="service_request_files")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    object_key = models.CharField(max_length=255, unique=True)
    content_type = models.CharField(max_length=128, blank=True)
    original_filename = models.CharField(max_length=255, blank=True, default="")
    size_bytes = models.PositiveBigIntegerField(default=0)
    owner_user_id = models.BigIntegerField()
    file_policy_name = models.CharField(max_length=64, default="documents")
    file_policy_version = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    attached_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.only(
                "attached_at", "owner_user_id", "object_key", "size_bytes", "content_type", "original_filename",
                "file_policy_name", "file_policy_version",
            ).get(pk=self.pk)
            if original.attached_at and any(
                getattr(self, field) != getattr(original, field)
                for field in (
                    "owner_user_id", "object_key", "size_bytes", "content_type", "original_filename",
                    "file_policy_name", "file_policy_version",
                )
            ):
                raise RuntimeError("Attached ServiceRequestFile metadata is immutable.")
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.kind}:{self.object_key}"


class ServiceRequestConsumptionQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise RuntimeError("ServiceRequestConsumption rows are append-only.")

    def delete(self):
        raise RuntimeError("ServiceRequestConsumption rows are append-only.")


class ServiceRequestConsumption(models.Model):
    class Measurement(models.TextChoices):
        COUNT = "count", "Count"
        GRAMS = "grams", "Grams"

    class Outcome(models.TextChoices):
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    service_request = models.ForeignKey(MachineServiceRequest, on_delete=models.PROTECT, related_name="consumptions")
    machine_consumable = models.ForeignKey("machines.MachineConsumable", on_delete=models.PROTECT, related_name="service_request_consumptions")
    measurement = models.CharField(max_length=10, choices=Measurement.choices)
    product = models.ForeignKey("inventory.InventoryProduct", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    label = models.CharField(max_length=200, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    outcome = models.CharField(max_length=16, choices=Outcome.choices)

    objects = ServiceRequestConsumptionQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["service_request", "machine_consumable"], name="uniq_service_request_consumable"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="service_req_consumption_qty_positive"),
        ]
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise RuntimeError("ServiceRequestConsumption rows are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("ServiceRequestConsumption rows are append-only.")
