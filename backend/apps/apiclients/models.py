import secrets

from django.conf import settings
from django.db import models

from apps.apiclients.crypto import decrypt_secret, encrypt_secret
from apps.makerspaces.models import Makerspace


def generate_client_id():
    return f"ck_{secrets.token_urlsafe(18)}"


class ApiClient(models.Model):
    """A signed API client (client_id + HMAC secret) scoped to a makerspace.

    Secret is stored ENCRYPTED (Fernet), not hashed - HMAC verification needs the raw
    secret back. `makerspace=None` is a global client (superadmin only)."""

    label = models.CharField(max_length=200)
    client_id = models.CharField(
        max_length=64, unique=True, default=generate_client_id, editable=False
    )
    secret_encrypted = models.BinaryField(editable=False)
    client_type = models.CharField(
        max_length=20,
        choices=[
            ("browser", "Browser"),
            ("server", "Server"),
        ],
        default="server",
    )
    scopes = models.JSONField(default=list, blank=True)
    rate_limit_tier = models.CharField(
        max_length=20,
        choices=[
            ("public", "Public"),
            ("standard", "Standard"),
            ("trusted", "Trusted"),
        ],
        default="standard",
    )
    makerspace = models.ForeignKey(
        Makerspace, null=True, blank=True, on_delete=models.CASCADE,
        related_name="api_clients",
    )
    allowed_origins = models.JSONField(default=list, blank=True)  # exact scheme://host[:port]
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="created_api_clients",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_secret(self, raw):
        self.secret_encrypted = encrypt_secret(raw)

    def get_secret(self):
        return decrypt_secret(self.secret_encrypted)

    def clean(self):
        # review fix #4: an HMAC client must restrict to at least one exact origin.
        from django.core.exceptions import ValidationError

        if not self.allowed_origins:
            raise ValidationError(
                {"allowed_origins": "At least one allowed origin is required."}
            )

    @classmethod
    def issue(
        cls,
        *,
        label,
        makerspace=None,
        allowed_origins=None,
        created_by=None,
        client_type="browser",
        scopes=None,
        rate_limit_tier="standard",
    ):
        raw = secrets.token_urlsafe(32)
        obj = cls(
            label=label,
            makerspace=makerspace,
            allowed_origins=allowed_origins or [],
            created_by=created_by,
            client_type=client_type,
            scopes=scopes or [],
            rate_limit_tier=rate_limit_tier,
        )
        obj.set_secret(raw)
        obj.save()
        return obj, raw  # raw secret shown to the operator exactly once

    def __str__(self):
        return f"{self.label} ({self.client_id})"
