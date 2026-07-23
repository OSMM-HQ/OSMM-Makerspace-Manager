import uuid

from django.conf import settings
from django.db import models


class DevicePlatform(models.TextChoices):
    APPLE = 'apple', 'Apple'
    ANDROID = 'android', 'Android'


class DeviceEnvironment(models.TextChoices):
    DEVELOPMENT = 'development', 'Development'
    PRODUCTION = 'production', 'Production'


class DeviceAttestationChallenge(models.Model):
    platform = models.CharField(max_length=16, choices=DevicePlatform.choices)
    app_id = models.CharField(max_length=255)
    signing_identity = models.CharField(max_length=255)
    environment = models.CharField(max_length=16, choices=DeviceEnvironment.choices)
    challenge_digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['expires_at', 'consumed_at'], name='device_challenge_use_idx')]


class DeviceGrant(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        REVOKED = 'revoked', 'Revoked'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='device_grants',
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    platform = models.CharField(max_length=16, choices=DevicePlatform.choices)
    app_id = models.CharField(max_length=255)
    signing_identity = models.CharField(max_length=255)
    environment = models.CharField(max_length=16, choices=DeviceEnvironment.choices)
    attestation_subject_fingerprint = models.CharField(max_length=64)
    attested_at = models.DateTimeField()
    last_used_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'status'], name='device_grant_user_idx')]


class DeviceRefreshFamily(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grant = models.ForeignKey(
        DeviceGrant,
        on_delete=models.CASCADE,
        related_name='refresh_families',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='device_refresh_families',
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    reuse_detected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['grant', 'revoked_at'], name='device_family_grant_idx')]


class DeviceRefreshToken(models.Model):
    family = models.ForeignKey(
        DeviceRefreshFamily,
        on_delete=models.CASCADE,
        related_name='tokens',
    )
    jti = models.CharField(max_length=255, unique=True)
    token_fingerprint = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    rotated_at = models.DateTimeField(null=True, blank=True)
    blacklisted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['family', 'rotated_at'], name='device_refresh_family_idx')]
