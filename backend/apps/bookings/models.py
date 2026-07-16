from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from apps.forms_schema.validation import validate_form_schema


class BookableSpace(models.Model):
    class Kind(models.TextChoices):
        DEV_ROOM = "dev_room", "Development room"
        BENCH = "bench", "Bench"
        MEETING = "meeting", "Meeting room"
        OTHER = "other", "Other"

    class ApprovalMode(models.TextChoices):
        INSTANT = 'instant', 'Instant confirmation'
        APPROVE = 'approve', 'Staff approval required'

    public_token = models.UUIDField(
        default=uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )
    makerspace = models.ForeignKey(
        "makerspaces.Makerspace",
        on_delete=models.CASCADE,
        related_name="bookable_spaces",
    )
    name = models.CharField(max_length=200)
    kind = models.CharField(
        max_length=16,
        choices=Kind.choices,
        default=Kind.OTHER,
    )
    description = models.TextField(blank=True)
    capacity = models.PositiveIntegerField(default=0)
    location = models.CharField(max_length=255, blank=True)
    image_key = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        default=None,
    )
    is_public = models.BooleanField(default=False)
    show_public_availability = models.BooleanField(default=False)
    show_public_booker_names = models.BooleanField(default=False)
    approval_mode = models.CharField(
        max_length=16,
        choices=ApprovalMode.choices,
        default=ApprovalMode.INSTANT,
    )
    custom_form = models.JSONField(
        null=True,
        blank=True,
        default=None,
        validators=[validate_form_schema],
    )
    requester_notifications_enabled = models.BooleanField(
        null=True,
        blank=True,
        default=None,
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(capacity__gte=0),
                name="bookspace_capacity_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=["makerspace", "is_active", "name"],
                name="bookspace_ms_active_idx",
            ),
            models.Index(
                fields=["makerspace", "is_public", "is_active"],
                name="bookspace_public_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        self.name = (self.name or "").strip()
        if not self.name:
            raise ValidationError({"name": "This field may not be blank."})
        if self.pk:
            original = type(self).objects.only("public_token", "makerspace_id").get(
                pk=self.pk
            )
            self.public_token = original.public_token
            self.makerspace_id = original.makerspace_id
        super().save(*args, **kwargs)


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"
        NO_SHOW = "no_show", "No-show"

    space = models.ForeignKey(
        BookableSpace,
        on_delete=models.CASCADE,
        related_name="bookings",
    )
    public_token = models.UUIDField(
        default=uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )
    name = models.CharField(max_length=200)
    email = models.EmailField(max_length=254)
    phone = models.CharField(max_length=32)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.CONFIRMED,
    )
    note = models.TextField(blank=True)
    custom_answers = models.JSONField(null=True, blank=True, default=None)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["starts_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")),
                name="booking_end_after_start",
            ),
        ]
        indexes = [
            models.Index(
                fields=["space", "status", "starts_at"],
                name="booking_space_status_idx",
            ),
            models.Index(
                fields=["space", "ends_at"],
                name="booking_space_end_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        self.name = (self.name or "").strip()
        self.email = (self.email or "").strip().lower()
        self.phone = (self.phone or "").strip()
        errors = {
            field: "This field may not be blank."
            for field in ("name", "email", "phone")
            if not getattr(self, field)
        }
        if errors:
            raise ValidationError(errors)
        if self.pk:
            original = type(self).objects.only("public_token", "space_id").get(
                pk=self.pk
            )
            self.public_token = original.public_token
            self.space_id = original.space_id
        super().save(*args, **kwargs)
