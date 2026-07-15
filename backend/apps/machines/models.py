from django.conf import settings
from django.db import models
from django.db.models import Q


class MachineType(models.Model):
    """Machine type catalog. Global built-ins (makerspace=NULL) + per-lab custom rows."""

    makerspace = models.ForeignKey(
        "makerspaces.Makerspace",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="machine_types",
    )
    slug = models.SlugField(max_length=50)
    name = models.CharField(max_length=200)
    icon = models.CharField(max_length=50, blank=True)
    is_builtin = models.BooleanField(default=False)
    # Server-controlled authorization hook: the rbac.Action a holder of which may
    # manage machines of this type (e.g. 3d_printer -> "MANAGE_PRINTING"). Blank for
    # custom types. Never client-settable.
    managing_action = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["makerspace__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["slug"],
                condition=Q(makerspace__isnull=True),
                name="uniq_global_machinetype_slug",
            ),
            models.UniqueConstraint(
                fields=["makerspace", "slug"],
                condition=Q(makerspace__isnull=False),
                name="uniq_lab_machinetype_slug",
            ),
            models.CheckConstraint(
                condition=(
                    Q(is_builtin=True, makerspace__isnull=True)
                    | Q(is_builtin=False, makerspace__isnull=False)
                ),
                name="machinetype_builtin_is_global",
            ),
        ]

    def __str__(self):
        return self.name


class Machine(models.Model):
    class Status(models.TextChoices):
        IDLE = "idle", "Idle"
        RUNNING = "running", "Running"
        RESERVED = "reserved", "Reserved"
        MAINTENANCE = "maintenance", "Maintenance"
        OFFLINE = "offline", "Offline"

    makerspace = models.ForeignKey(
        "makerspaces.Makerspace",
        on_delete=models.CASCADE,
        related_name="machines",
    )
    machine_type = models.ForeignKey(
        MachineType,
        on_delete=models.PROTECT,
        related_name="machines",
    )
    name = models.CharField(max_length=200)
    location = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.IDLE
    )
    firmware_version = models.CharField(max_length=100, blank=True)
    camera_feed_url = models.URLField(blank=True)
    image_key = models.CharField(max_length=300, blank=True, default="")
    is_active = models.BooleanField(default=True)
    # Set only by the linking service; read-only over REST/admin.
    linked_print_printer = models.OneToOneField(
        "printing.PrintPrinter",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="machine",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["makerspace__name", "name"]

    def __str__(self):
        return self.name


class MachineOperator(models.Model):
    """Per-machine operator assignment (many-to-many with an access level)."""

    class AccessLevel(models.TextChoices):
        OPERATE = "operate", "Operate"
        MANAGE = "manage", "Manage"
        FULL = "full", "Full"

    machine = models.ForeignKey(
        Machine, on_delete=models.CASCADE, related_name="operators"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    access_level = models.CharField(max_length=16, choices=AccessLevel.choices)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("machine", "user")
        ordering = ["-assigned_at"]

    def __str__(self):
        return f"{self.user} @ {self.machine} ({self.access_level})"


class MachineUsageEntry(models.Model):
    """Append-only usage-hours ledger. Machine total is derived via Sum."""

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"

    machine = models.ForeignKey(
        Machine, on_delete=models.CASCADE, related_name="usage_entries"
    )
    hours = models.DecimalField(max_digits=10, decimal_places=2)
    source = models.CharField(
        max_length=16, choices=Source.choices, default=Source.MANUAL
    )
    note = models.CharField(max_length=255, blank=True)
    logged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(hours__gt=0),
                name="machineusage_hours_positive",
            ),
        ]

    def __str__(self):
        return f"{self.machine}: {self.hours}h"


class MachineDocument(models.Model):
    """Manuals / SOP documents in the private object-storage bucket."""

    class DocType(models.TextChoices):
        MANUAL = "manual", "Manual"
        SOP = "sop", "SOP"

    machine = models.ForeignKey(
        Machine, on_delete=models.CASCADE, related_name="documents"
    )
    doc_type = models.CharField(max_length=16, choices=DocType.choices)
    object_key = models.CharField(max_length=255, unique=True)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveBigIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.doc_type}: {self.original_filename}"


class MachineErrorLog(models.Model):
    """Append-only machine technical-fault log (distinct from M2 Incident Reporting)."""

    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"
        CRITICAL = "critical", "Critical"

    machine = models.ForeignKey(
        Machine, on_delete=models.CASCADE, related_name="error_logs"
    )
    severity = models.CharField(max_length=16, choices=Severity.choices)
    message = models.TextField()
    logged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.severity} @ {self.machine}"
