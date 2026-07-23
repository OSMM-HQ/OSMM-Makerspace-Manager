from django.conf import settings
from django.db import models

from apps.makerspaces.secrets import decrypt_value, encrypt_value


class PlatformPushSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    fcm_service_account = models.TextField(blank=True, default="")
    apns_private_key = models.TextField(blank=True, default="")
    apns_team_id = models.CharField(max_length=64, blank=True, default="")
    apns_key_id = models.CharField(max_length=64, blank=True, default="")
    apns_topic = models.CharField(max_length=255, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def set_fcm_service_account(self, raw):
        self.fcm_service_account = encrypt_value(raw) if raw else ""

    def get_fcm_service_account(self):
        return decrypt_value(self.fcm_service_account) if self.fcm_service_account else ""

    def set_apns_private_key(self, raw):
        self.apns_private_key = encrypt_value(raw) if raw else ""

    def get_apns_private_key(self):
        return decrypt_value(self.apns_private_key) if self.apns_private_key else ""

    @property
    def fcm_configured(self):
        return bool(self.fcm_service_account)

    @property
    def apns_configured(self):
        return bool(self.apns_private_key and self.apns_team_id and self.apns_key_id and self.apns_topic)

    def __str__(self):
        return "Platform push settings"


class PushDevice(models.Model):
    class Provider(models.TextChoices):
        FCM = "fcm", "FCM"
        APNS = "apns", "APNs"

    class Environment(models.TextChoices):
        DEVELOPMENT = "development", "Development"
        PRODUCTION = "production", "Production"

    token_ciphertext = models.TextField()
    token_fingerprint = models.CharField(max_length=64)
    provider = models.CharField(max_length=8, choices=Provider.choices)
    environment = models.CharField(max_length=16, choices=Environment.choices)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_devices")
    makerspace = models.ForeignKey("makerspaces.Makerspace", on_delete=models.CASCADE, related_name="push_devices")
    device_grant = models.ForeignKey("accounts.DeviceGrant", on_delete=models.CASCADE, related_name="push_devices")
    active = models.BooleanField(default=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["makerspace", "provider", "environment", "token_fingerprint"],
            name="uniq_push_token_fingerprint",
        )]
        indexes = [models.Index(
            fields=["makerspace", "active", "provider"], name="push_device_active_idx"
        )]

    def set_token(self, raw):
        self.token_ciphertext = encrypt_value(raw)

    def get_token(self):
        return decrypt_value(self.token_ciphertext)
