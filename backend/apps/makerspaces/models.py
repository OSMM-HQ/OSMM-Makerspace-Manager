from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Makerspace(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, db_index=True)
    location = models.CharField(max_length=200, blank=True)
    public_inventory_enabled = models.BooleanField(default=True)
    telegram_group_chat_id = models.CharField(max_length=64, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_makerspaces",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.name


class MakerspaceMembership(models.Model):
    # Role is per-makerspace: this membership is what grants a user admin/guest-admin
    # rights for THIS makerspace. Global User.role stays for superadmin. Enforcement
    # of scoping/suspension is centralized in the Phase 2 RBAC layer, not here.
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        GUEST_ADMIN = "guest_admin", "Guest Admin"
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
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.ADMIN)
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
