import uuid

from django.conf import settings
from django.db import models


class HardwareRequest(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_APPROVAL = "pending_approval", "Pending Approval"
        REJECTED = "rejected", "Rejected"
        ACCEPTED = "accepted", "Accepted"
        ISSUED = "issued", "Issued"
        PARTIALLY_RETURNED = "partially_returned", "Partially Returned"
        RETURNED = "returned", "Returned"
        CLOSED_WITH_ISSUE = "closed_with_issue", "Closed with Issue"

    makerspace = models.ForeignKey(
        "makerspaces.Makerspace",
        on_delete=models.CASCADE,
        related_name="hardware_requests",
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="hardware_requests",
    )
    requester_username = models.CharField(max_length=150)
    requester_contact_email = models.EmailField(blank=True)
    requester_contact_phone = models.CharField(max_length=32, blank=True)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING_APPROVAL,
        db_index=True,
    )
    requested_for = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    accepted_at = models.DateTimeField(null=True)
    assigned_box = models.ForeignKey(
        "boxes.Box",
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    issued_at = models.DateTimeField(null=True)
    return_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    return_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    issue_evidence = models.OneToOneField(
        "evidence.EvidencePhoto",
        null=True,
        on_delete=models.PROTECT,
        related_name="issued_request",
    )
    issue_remark = models.TextField(blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    closed_at = models.DateTimeField(null=True)
    public_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["makerspace", "status"]),
            models.Index(
                fields=["makerspace", "status", "-created_at"],
                name="hwreq_ms_status_created_idx",
            ),
            models.Index(
                fields=["makerspace", "status", "-issued_at", "-created_at"],
                name="hwreq_ms_status_issued_idx",
            ),
            models.Index(
                fields=["makerspace", "status", "-updated_at", "-created_at"],
                name="hwreq_ms_status_updated_idx",
            ),
            models.Index(
                fields=["makerspace", "status", "-closed_at"],
                name="hwreq_ms_status_closed_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["assigned_box"],
                condition=models.Q(
                    status__in=[
                        "issued",
                        "partially_returned",
                    ]
                ),
                name="uniq_active_loan_per_box",
            ),
        ]


class HardwareRequestItem(models.Model):
    request = models.ForeignKey(
        HardwareRequest,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        "inventory.InventoryProduct",
        on_delete=models.PROTECT,
        related_name="+",
    )
    requested_quantity = models.PositiveIntegerField()
    accepted_quantity = models.PositiveIntegerField(default=0)
    issued_quantity = models.PositiveIntegerField(default=0)
    returned_quantity = models.PositiveIntegerField(default=0)
    damaged_quantity = models.PositiveIntegerField(default=0)
    missing_quantity = models.PositiveIntegerField(default=0)
    # Units rejected as broken at handover (never issued; sent to the needs_fix bucket).
    needs_fix_quantity = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(requested_quantity__gte=1),
                name="req_item_qty_positive",
            ),
        ]


class HardwareEmailTemplate(models.Model):
    class Key(models.TextChoices):
        REQUEST_RECEIVED = "request_received", "Request Received"
        REQUEST_ACCEPTED = "request_accepted", "Request Accepted"
        REQUEST_REJECTED = "request_rejected", "Request Rejected"
        REQUEST_ISSUED = "request_issued", "Request Issued"
        REQUEST_RETURNED = "request_returned", "Request Returned"
        RETURN_REMINDER = "return_reminder", "Return Reminder"

    makerspace = models.ForeignKey(
        "makerspaces.Makerspace",
        on_delete=models.CASCADE,
        related_name="hardware_email_templates",
    )
    key = models.CharField(max_length=32, choices=Key.choices)
    subject = models.CharField(max_length=200)
    text_body = models.TextField()
    html_body = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["makerspace", "key"],
                name="uniq_hardware_email_template_key_per_space",
            )
        ]
        ordering = ["makerspace__name", "key"]

    def __str__(self):
        return f"{self.makerspace}: {self.get_key_display()}"


from apps.hardware_requests.return_models import (  # noqa: E402
    RequesterAccountability,
    ReturnEvent,
)
from apps.hardware_requests.asset_link_models import HardwareRequestItemAsset  # noqa: E402
from apps.hardware_requests.self_checkout_models import PublicToolLoan  # noqa: E402
