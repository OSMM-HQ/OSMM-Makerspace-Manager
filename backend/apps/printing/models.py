import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class PrintBucket(models.Model):
    makerspace = models.ForeignKey(
        "makerspaces.Makerspace",
        on_delete=models.CASCADE,
        related_name="print_buckets",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["makerspace", "name"],
                name="uniq_print_bucket_makerspace_name",
            ),
        ]
        ordering = ["makerspace__name", "name"]

    def __str__(self):
        return f"{self.makerspace}: {self.name}"


class PrintPrinter(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        MAINTENANCE = "maintenance", "Maintenance"
        OFFLINE = "offline", "Offline"

    makerspace = models.ForeignKey(
        "makerspaces.Makerspace",
        on_delete=models.CASCADE,
        related_name="print_printers",
    )
    name = models.CharField(max_length=200)
    model = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["makerspace", "name"],
                name="uniq_print_printer_makerspace_name",
            ),
        ]
        ordering = ["makerspace__name", "name"]

    def __str__(self):
        return f"{self.makerspace}: {self.name}"


class FilamentSpool(models.Model):
    makerspace = models.ForeignKey(
        "makerspaces.Makerspace",
        on_delete=models.CASCADE,
        related_name="filament_spools",
    )
    printer = models.ForeignKey(
        PrintPrinter,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="filament_spools",
    )
    material = models.CharField(max_length=100)
    color = models.CharField(max_length=100, blank=True)
    brand = models.CharField(max_length=100, blank=True)
    lot_code = models.CharField(max_length=100, blank=True)
    initial_weight_grams = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    remaining_weight_grams = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    is_active = models.BooleanField(default=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["makerspace__name", "printer__name", "material", "color"]

    def __str__(self):
        color = f" {self.color}" if self.color else ""
        return f"{self.material}{color} ({self.remaining_weight_grams}g left)"


class ManualPrintLog(models.Model):
    makerspace = models.ForeignKey(
        "makerspaces.Makerspace",
        on_delete=models.CASCADE,
        related_name="manual_print_logs",
    )
    printer = models.ForeignKey(
        PrintPrinter,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="manual_print_logs",
    )
    filament_spool = models.ForeignKey(
        FilamentSpool,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="manual_print_logs",
    )
    grams_used = models.DecimalField(max_digits=8, decimal_places=2)
    title = models.CharField(max_length=200)
    note = models.TextField(blank=True)
    logged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(grams_used__gt=0),
                name="manual_print_log_grams_positive",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.grams_used}g)"


class PrintRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        PRINTING = "printing", "Printing"
        COMPLETED = "completed", "Completed"
        COLLECTED = "collected", "Collected"
        REJECTED = "rejected", "Rejected"
        FAILED = "failed", "Failed"

    class PaymentStatus(models.TextChoices):
        NONE = "none", "None"
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"

    bucket = models.ForeignKey(
        PrintBucket,
        on_delete=models.PROTECT,
        related_name="print_requests",
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="print_requests",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    material = models.CharField(max_length=100, blank=True)
    color = models.CharField(max_length=100, blank=True)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    source_link = models.URLField(blank=True)
    model_file = models.FileField(
        upload_to="printing/models/%Y/%m/",
        blank=True,
        validators=[FileExtensionValidator(["stl", "3mf", "step", "stp", "obj"])],
    )
    preferred_settings = models.TextField(blank=True)
    estimate_screenshot = models.FileField(
        upload_to="printing/estimates/%Y/%m/",
        blank=True,
        validators=[FileExtensionValidator(["png", "jpg", "jpeg", "webp", "pdf"])],
    )
    preview_screenshot = models.FileField(
        upload_to="printing/previews/%Y/%m/",
        blank=True,
        validators=[FileExtensionValidator(["png", "jpg", "jpeg", "webp", "pdf"])],
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    reason = models.TextField(blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="handled_print_requests",
    )
    printer = models.ForeignKey(
        PrintPrinter,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="print_requests",
    )
    filament_spool = models.ForeignKey(
        FilamentSpool,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="print_requests",
    )
    requested_filament_spool = models.ForeignKey(
        "printing.FilamentSpool",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requested_for_print_requests",
    )
    estimated_minutes = models.PositiveIntegerField(default=0)
    estimated_filament_grams = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    payment_status = models.CharField(
        max_length=16,
        choices=PaymentStatus.choices,
        default=PaymentStatus.NONE,
        db_index=True,
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    collected_at = models.DateTimeField(null=True, blank=True)
    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="collected_print_requests",
    )
    filament_grams_used = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
    )
    filament_grams_reserved = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    reprint_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reprints",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    public_token = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )
    project_brief = models.TextField(blank=True)
    requester_name = models.CharField(max_length=120, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["requester", "-created_at"],
                name="printreq_requester_created_idx",
            ),
            models.Index(
                fields=["bucket", "status", "-created_at"],
                name="printreq_bucket_status_idx",
            ),
            models.Index(
                fields=["bucket", "payment_status", "status"],
                name="printreq_bucket_payment_idx",
            ),
        ]
        ordering = ["-created_at"]

    @property
    def makerspace(self):
        return self.bucket.makerspace

    @property
    def makerspace_id(self):
        return self.bucket.makerspace_id

    def __str__(self):
        return f"{self.title} ({self.status})"


class PrintRequestFile(models.Model):
    class Kind(models.TextChoices):
        STL = "stl", "STL"
        SCREENSHOT = "screenshot", "Screenshot"

    print_request = models.ForeignKey(
        PrintRequest,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="files",
    )
    makerspace = models.ForeignKey(
        "makerspaces.Makerspace",
        on_delete=models.CASCADE,
        related_name="print_request_files",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    object_key = models.CharField(max_length=255, unique=True)
    content_type = models.CharField(max_length=128, blank=True)
    original_filename = models.CharField(max_length=255, blank=True, default="")
    size_bytes = models.PositiveBigIntegerField(default=0)
    owner_checkin_user_id = models.CharField(max_length=255, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    attached_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.kind}:{self.object_key}"
