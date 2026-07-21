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
