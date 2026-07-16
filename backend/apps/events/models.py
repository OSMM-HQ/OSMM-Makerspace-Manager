from uuid import uuid4

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Event(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    public_token = models.UUIDField(
        default=uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )
    makerspace = models.ForeignKey(
        "makerspaces.Makerspace",
        on_delete=models.CASCADE,
        related_name="events",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    location = models.CharField(max_length=255, blank=True)
    capacity = models.PositiveIntegerField(default=0)
    is_public = models.BooleanField(default=False)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
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
        ordering = ["starts_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gte=F("starts_at")),
                name="event_ends_not_before_start",
            ),
            models.CheckConstraint(
                condition=Q(capacity__gte=0),
                name="event_capacity_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=["makerspace", "starts_at"],
                name="event_ms_starts_idx",
            ),
            models.Index(
                fields=["makerspace", "status", "starts_at"],
                name="event_ms_status_start_idx",
            ),
            models.Index(
                fields=["makerspace", "is_public", "status", "ends_at"],
                name="event_public_lookup_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        self.title = (self.title or "").strip()
        if self.pk:
            original = type(self).objects.only("public_token", "makerspace_id").get(
                pk=self.pk
            )
            self.public_token = original.public_token
            self.makerspace_id = original.makerspace_id
        super().save(*args, **kwargs)


class EventRegistration(models.Model):
    class Status(models.TextChoices):
        REGISTERED = "registered", "Registered"
        WAITLISTED = "waitlisted", "Waitlisted"
        CANCELLED = "cancelled", "Cancelled"
        ATTENDED = "attended", "Attended"

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="registrations",
    )
    name = models.CharField(max_length=200)
    email = models.EmailField(max_length=254)
    phone = models.CharField(max_length=32)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.REGISTERED,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "email"],
                name="uniq_event_registration_email",
            ),
        ]
        indexes = [
            models.Index(
                fields=["event", "status", "created_at"],
                name="eventreg_status_fifo_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        self.name = (self.name or "").strip()
        self.email = (self.email or "").strip().lower()
        self.phone = (self.phone or "").strip()
        super().save(*args, **kwargs)
