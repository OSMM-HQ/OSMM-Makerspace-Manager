from django.db import models
from django.db.models import Q


class EncryptionKeyQuerySet(models.QuerySet):
    def delete(self):
        raise RuntimeError("Encryption key rows cannot be deleted.")


class EncryptionKeyManager(models.Manager.from_queryset(EncryptionKeyQuerySet)):
    pass


class MakerspaceEncryptionKey(models.Model):
    class BrokerBackend(models.TextChoices):
        LOCAL = "local", "Local master key"
        AWS_KMS = "aws_kms", "AWS KMS"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ROTATED = "rotated", "Rotated"
        DISABLED = "disabled", "Disabled"

    makerspace = models.ForeignKey(
        "makerspaces.Makerspace",
        on_delete=models.PROTECT,
        related_name="encryption_keys",
    )
    version = models.PositiveIntegerField()
    wrapped_dek = models.BinaryField()
    broker_backend = models.CharField(max_length=16, choices=BrokerBackend.choices)
    broker_key_id = models.CharField(max_length=255)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    rotated_at = models.DateTimeField(null=True, blank=True)
    disabled_at = models.DateTimeField(null=True, blank=True)

    objects = EncryptionKeyManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["makerspace", "version"], name="uniq_makerspace_dek_version"
            ),
            models.UniqueConstraint(
                fields=["makerspace"],
                condition=Q(status="active"),
                name="uniq_makerspace_active_dek",
            ),
            models.CheckConstraint(
                condition=Q(version__gte=1), name="ck_makerspace_dek_version_positive"
            ),
        ]
        indexes = [models.Index(fields=["makerspace", "status"])]

    def delete(self, *args, **kwargs):
        raise RuntimeError("Encryption key rows cannot be deleted.")
