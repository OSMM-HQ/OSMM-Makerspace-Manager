from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from apps.makerspaces.secrets import decrypt_value, encrypt_value


currency_validator = RegexValidator(
    regex=r"^[a-z]{3}$",
    message="Default currency must be a three-letter lowercase ISO currency code.",
)


class MakerspacePaymentSettings(models.Model):
    """Stripe credentials owned by one makerspace and encrypted at rest."""

    makerspace = models.OneToOneField(
        "makerspaces.Makerspace",
        on_delete=models.CASCADE,
        related_name="payment_settings",
    )
    stripe_secret_key = models.TextField(blank=True, default="")
    stripe_webhook_secret = models.TextField(blank=True, default="")
    default_currency = models.CharField(
        max_length=3,
        default="usd",
        validators=[currency_validator],
    )

    class Meta:
        verbose_name = "makerspace payment settings"
        verbose_name_plural = "makerspace payment settings"

    def __str__(self):
        return f"Payments: {self.makerspace}"

    @classmethod
    def for_makerspace(cls, makerspace):
        return cls.objects.filter(makerspace=makerspace).first() or cls(makerspace=makerspace)

    @property
    def is_configured(self):
        return bool(self.stripe_secret_key and self.stripe_webhook_secret)

    def clean(self):
        self.default_currency = (self.default_currency or "").strip().lower()
        try:
            currency_validator(self.default_currency)
        except ValidationError:
            raise ValidationError({"default_currency": "Enter a three-letter lowercase currency code."})

    def save(self, *args, **kwargs):
        self.default_currency = (self.default_currency or "").strip().lower()
        self.full_clean()
        return super().save(*args, **kwargs)

    def set_stripe_secret_key(self, raw):
        self.stripe_secret_key = encrypt_value(raw)

    def get_stripe_secret_key(self):
        return decrypt_value(self.stripe_secret_key)

    def set_stripe_webhook_secret(self, raw):
        self.stripe_webhook_secret = encrypt_value(raw)

    def get_stripe_webhook_secret(self):
        return decrypt_value(self.stripe_webhook_secret)


class Payment(models.Model):
    """The durable, single authority for an amount owed by a domain subject."""

    class SubjectType(models.TextChoices):
        MACHINE_SERVICE_REQUEST = "machine_service_request", "Machine service request"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID_ONLINE = "paid_online", "Paid online"
        PAID_OFFLINE = "paid_offline", "Paid offline"
        WAIVED = "waived", "Waived"
        CANCELED = "canceled", "Canceled"

    makerspace = models.ForeignKey("makerspaces.Makerspace", on_delete=models.PROTECT, related_name="payments")
    subject_type = models.CharField(max_length=48, choices=SubjectType.choices)
    subject_id = models.PositiveBigIntegerField()
    member = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, validators=[currency_validator])
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    stripe_checkout_session_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    stripe_checkout_url = models.URLField(blank=True, default="")
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
            original = type(self).objects.filter(pk=self.pk).values("status", "amount").first()
            if original and original["status"] != self.Status.PENDING and (original["status"] != self.status or original["amount"] != self.amount):
                raise ValidationError("Terminal payments are immutable.")
        self.full_clean()
        return super().save(*args, **kwargs)


class ProcessedStripeEvent(models.Model):
    makerspace = models.ForeignKey("makerspaces.Makerspace", on_delete=models.PROTECT, related_name="processed_stripe_events")
    stripe_event_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["makerspace", "stripe_event_id"], name="stripe_event_once_per_makerspace")]
