"""Persistent B4 cutover controls and non-destructive repair evidence."""

from django.conf import settings
from django.db import models


class PrintingCutoverState(models.Model):
    """Singleton-like per-makerspace authority marker.

    It is deliberately data, rather than an environment toggle: a deployment can
    prove reconciliation before enabling kernel writes and a later deployment
    cannot silently re-enable legacy writes.
    """

    makerspace = models.OneToOneField(
        "makerspaces.Makerspace", on_delete=models.CASCADE, related_name="printing_cutover_state"
    )
    kernel_authoritative_at = models.DateTimeField(null=True, blank=True)
    reconciled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def kernel_authoritative(self):
        return self.kernel_authoritative_at is not None


class PrintingCutoverRepair(models.Model):
    """An explicit forward-repair queue; imported history is never edited."""

    class Kind(models.TextChoices):
        INVALID_SOURCE = "invalid_source", "Invalid legacy source"
        MISMATCH = "mismatch", "Reconciliation mismatch"
        MISSING_OBJECT = "missing_object", "Missing storage object"
        COLLISION = "collision", "Provenance/object collision"
        WARRANTY = "warranty", "Unmapped warranty link"

    makerspace = models.ForeignKey("makerspaces.Makerspace", on_delete=models.CASCADE, related_name="printing_cutover_repairs")
    kind = models.CharField(max_length=32, choices=Kind.choices)
    legacy_model = models.CharField(max_length=100)
    legacy_id = models.PositiveIntegerField(null=True, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["makerspace", "kind", "legacy_model", "legacy_id"],
                name="uniq_print_cutover_repair_source",
            )
        ]
        ordering = ["created_at", "id"]

