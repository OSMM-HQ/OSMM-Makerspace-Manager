from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Warranty(models.Model):
    makerspace = models.ForeignKey(
        "makerspaces.Makerspace",
        on_delete=models.CASCADE,
        related_name="warranties",
    )
    asset = models.OneToOneField(
        "inventory.InventoryAsset",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="warranty",
    )
    printer = models.OneToOneField(
        "printing.PrintPrinter",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="warranty",
    )
    purchased_on = models.DateField(null=True, blank=True)
    warranty_expires_on = models.DateField(null=True, blank=True)
    vendor_name = models.CharField(max_length=200, blank=True)
    vendor_contact = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(asset__isnull=False, printer__isnull=True)
                    | models.Q(asset__isnull=True, printer__isnull=False)
                ),
                name="warranty_exactly_one_host",
            ),
        ]

    def clean(self):
        errors = {}
        if self.asset_id and self.asset.makerspace_id != self.makerspace_id:
            errors["asset"] = "Asset must belong to the same makerspace."
        if self.printer_id and self.printer.makerspace_id != self.makerspace_id:
            errors["printer"] = "Printer must belong to the same makerspace."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        if self.asset_id:
            return f"Warranty for asset {self.asset}"
        if self.printer_id:
            return f"Warranty for printer {self.printer}"
        return f"Warranty {self.pk}"


class WarrantyDocument(models.Model):
    warranty = models.ForeignKey(
        Warranty,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    object_key = models.CharField(max_length=300, unique=True)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.original_filename
