from django.core.exceptions import ValidationError
from django.db import models

from apps.payments.models_settings import currency_validator


class Payment(models.Model):
    class SubjectType(models.TextChoices):
        MACHINE_SERVICE_REQUEST = "machine_service_request", "Machine service request"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID_ONLINE = "paid_online", "Paid online"
        PAID_OFFLINE = "paid_offline", "Paid offline"
        WAIVED = "waived", "Waived"
        CANCELED = "canceled", "Canceled"

    class StripeProvider(models.TextChoices):
        RAW = "raw", "Makerspace raw credentials"
        CONNECT = "connect", "Stripe Connect"

    makerspace = models.ForeignKey("makerspaces.Makerspace", on_delete=models.PROTECT, related_name="payments")
    subject_type = models.CharField(max_length=48, choices=SubjectType.choices)
    subject_id = models.PositiveBigIntegerField()
    member = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, validators=[currency_validator])
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    stripe_provider = models.CharField(max_length=16, choices=StripeProvider.choices, default=StripeProvider.RAW)
    stripe_connected_account_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_application_fee_amount = models.PositiveBigIntegerField(default=0)
    stripe_checkout_session_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    stripe_checkout_url = models.URLField(blank=True, default="")
    stripe_checkout_session_expired_at = models.DateTimeField(null=True, blank=True)
    stripe_payment_intent_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="created_payments")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["makerspace", "subject_type", "subject_id"], name="payment_one_per_subject"),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="payment_amount_positive"),
        ]
        ordering = ["-created_at"]

    def clean(self):
        self.currency = (self.currency or "").lower()
        currency_validator(self.currency)
        if self.subject_type == self.SubjectType.MACHINE_SERVICE_REQUEST and self.subject_id:
            from apps.machines.models import MachineServiceRequest

            if not MachineServiceRequest.objects.filter(pk=self.subject_id, makerspace_id=self.makerspace_id).exists():
                raise ValidationError({"subject_id": "Payment subject must belong to the payment makerspace."})

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values(
                "status", "amount", "stripe_provider", "stripe_connected_account_id", "stripe_application_fee_amount"
            ).first()
            if original and original["status"] != self.Status.PENDING and (
                original["status"] != self.status or original["amount"] != self.amount
            ):
                raise ValidationError("Terminal payments are immutable.")
            if original and any(
                original[field] != getattr(self, field)
                for field in ("stripe_provider", "stripe_connected_account_id", "stripe_application_fee_amount")
            ):
                raise ValidationError("Stripe provenance is immutable.")
        self.full_clean()
        return super().save(*args, **kwargs)


class ProcessedStripeEvent(models.Model):
    makerspace = models.ForeignKey("makerspaces.Makerspace", on_delete=models.PROTECT, related_name="processed_stripe_events")
    stripe_event_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["makerspace", "stripe_event_id"], name="stripe_event_once_per_makerspace")]
