from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils.crypto import get_random_string

from apps.makerspaces.secrets import decrypt_value, encrypt_value


def generate_publishable_key():
    return f"pk_{get_random_string(32)}"


def generate_public_code():
    return get_random_string(4, allowed_chars="ABCDEFGHJKLMNPQRSTUVWXYZ23456789")


def normalize_frontend_domain(value):
    """Reduce a pasted domain/URL/origin to a bare lowercase host (or None).

    A staff member may paste `https://alpha.example/admin`; storing that raw would
    make the origin helpers build `https://https://alpha.example`. Extract just the
    host so `frontend_domain` is always a bare hostname.
    """
    raw = (value or "").strip().lower()
    if not raw:
        return None
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    return (parsed.hostname or "") or None


DEFAULT_ENABLED_MODULES = [
    "public_inventory",
    "request_workflow",
    "self_checkout",
    "staff_admin",
    "guest_handover",
    "scanner",
    "printing",
    "telegram",
    "evidence_uploads",
    "qr_management",
    "bulk_import",
    "containers",
    "stock_transfers",
    "stocktake",
    "reports",
    "qr_print_batches",
    "asset_units",
    "procurement",
]


def default_enabled_modules():
    return list(DEFAULT_ENABLED_MODULES)


def default_theme_config():
    return {
        "mode": "light",
        "primary_color": "#2563eb",
        "accent_color": "#16a34a",
        "logo_url": "",
    }


def default_branding_config():
    return {
        "display_name": "",
        "support_email": "",
        "support_url": "",
    }


class Makerspace(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, db_index=True)
    public_code = models.CharField(
        max_length=4,
        unique=True,
        db_index=True,
        default=generate_public_code,
        validators=[
            RegexValidator(
                regex=r"^[A-Z0-9]{4}$",
                message="Public code must be exactly 4 uppercase letters or digits.",
            )
        ],
    )
    location = models.CharField(max_length=200, blank=True)
    public_inventory_enabled = models.BooleanField(default=True)
    superadmin_access_enabled = models.BooleanField(default=True)
    staff_notifications_enabled = models.BooleanField(default=True)
    logo_key = models.CharField(max_length=300, blank=True, default="")
    cover_image_key = models.CharField(max_length=300, blank=True, default="")
    # Case-insensitive uniqueness is enforced by the Lower() UniqueConstraint in Meta
    # (which also covers exact duplicates); no field-level unique index needed.
    frontend_domain = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )
    hidden_from_central_directory = models.BooleanField(default=False)
    public_api_key = models.CharField(
        max_length=40,
        editable=False,
        default=generate_publishable_key,
    )
    cors_allowed_origins = models.JSONField(default=list, blank=True)
    enabled_modules = models.JSONField(default=default_enabled_modules, blank=True)
    theme_config = models.JSONField(default=default_theme_config, blank=True)
    branding_config = models.JSONField(default=default_branding_config, blank=True)
    telegram_group_chat_id = models.CharField(max_length=64, blank=True)
    telegram_bot_token = models.CharField(max_length=200, blank=True)
    smtp_host = models.CharField(max_length=200, blank=True)
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_username = models.CharField(max_length=200, blank=True)
    smtp_password = models.CharField(max_length=200, blank=True)
    smtp_use_tls = models.BooleanField(default=True)
    # Implicit SSL (port 465). Mutually exclusive with STARTTLS (smtp_use_tls):
    # when set, the mail connection ignores use_tls. Lets a makerspace use a
    # 465-only provider (e.g. Gmail implicit SSL) instead of STARTTLS on 587.
    smtp_use_ssl = models.BooleanField(default=False)
    smtp_from_email = models.EmailField(blank=True)
    default_loan_days = models.PositiveIntegerField(default=7)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_makerspaces",
    )
    # Soft-delete state. archived_at IS NOT NULL ⇒ archived (single source of truth; no
    # separate boolean). An archived makerspace is operationally unreachable for everyone
    # (excluded centrally in rbac + public surfaces) but stays visible to the superadmin in
    # the Django /control/ admin so it can be permanently purged.
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["public_api_key"],
                name="uniq_makerspace_public_api_key",
            ),
            models.UniqueConstraint(
                Lower("frontend_domain"),
                name="uniq_makerspace_frontend_domain_ci",
            ),
            models.CheckConstraint(
                condition=Q(hidden_from_central_directory=False)
                | Q(frontend_domain__isnull=False),
                name="ck_makerspace_hidden_requires_domain",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.public_code = (self.public_code or "").upper()
        self.frontend_domain = normalize_frontend_domain(self.frontend_domain)
        super().save(*args, **kwargs)

    def clean(self):
        if self.hidden_from_central_directory and not self.frontend_domain:
            raise ValidationError(
                {
                    "hidden_from_central_directory": (
                        "A frontend domain is required to hide a makerspace from the central directory."
                    )
                }
            )

    def set_telegram_bot_token(self, raw):
        self.telegram_bot_token = encrypt_value(raw)

    def get_telegram_bot_token(self):
        return decrypt_value(self.telegram_bot_token)

    def set_smtp_password(self, raw):
        self.smtp_password = encrypt_value(raw)

    def get_smtp_password(self):
        return decrypt_value(self.smtp_password)


class MakerspaceMembership(models.Model):
    # Role is per-makerspace: this membership is what grants a user space-manager/guest-admin
    # rights for THIS makerspace. Global User.role stays for superadmin. Enforcement
    # of scoping/suspension is centralized in the Phase 2 RBAC layer, not here.
    class Role(models.TextChoices):
        SPACE_MANAGER = "space_manager", "Space Manager"
        GUEST_ADMIN = "guest_admin", "Guest Admin"
        INVENTORY_MANAGER = "inventory_manager", "Inventory Manager"
        PRINT_MANAGER = "print_manager", "Print Manager"

    makerspace = models.ForeignKey(
        Makerspace,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="makerspace_memberships",
        limit_choices_to={"is_active": True},
    )
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.SPACE_MANAGER)
    # Per-makerspace opt-in for staff lifecycle email notifications. Default True keeps
    # existing behavior (every relevant manager is notified); the space manager can turn
    # an individual manager off in Settings without removing their access.
    receives_notifications = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["makerspace", "user"],
                name="uniq_makerspace_user",
            ),
        ]

    def clean(self):
        # Block assigning a membership to a deactivated account (covers the User-side
        # inline where user is the parent and limit_choices_to does not apply).
        if self.user_id and not self.user.is_active:
            raise ValidationError("Cannot assign a makerspace to an inactive user.")

    def __str__(self):
        return f"{self.user} @ {self.makerspace.slug} ({self.role})"
