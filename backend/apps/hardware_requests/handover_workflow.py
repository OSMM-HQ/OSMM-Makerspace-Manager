from django.db import IntegrityError, transaction
from django.utils import timezone
from datetime import timedelta

from apps.audit import services as audit
from apps.boxes.models import Box, BoxScan
from apps.evidence import storage
from apps.evidence.models import EvidencePhoto
from apps.hardware_requests import notifications
from apps.hardware_requests.models import HardwareRequest
from apps.hardware_requests.workflow_errors import (
    BoxUnavailable,
    BoxValidationError,
    EvidenceNotUploaded,
    InvalidTransition,
    RequestValidationError,
)
from apps.hardware_requests.workflow_utils import constraint_name, locked_request
from apps.inventory import availability


def assign_box(actor, request, box_code):
    with transaction.atomic():
        locked = locked_request(request)
        if locked.status != HardwareRequest.Status.ACCEPTED:
            raise InvalidTransition(
                f"Cannot assign box for hardware request with status {locked.status}."
            )

        box = Box.objects.filter(
            makerspace=locked.makerspace,
            code=box_code,
            is_active=True,
        ).first()
        if box is None:
            raise BoxValidationError("Unknown or inactive box.")

        occupied = HardwareRequest.objects.filter(
            assigned_box=box,
            status__in=[
                HardwareRequest.Status.ISSUED,
                HardwareRequest.Status.PARTIALLY_RETURNED,
            ],
        ).exclude(pk=locked.pk)
        if occupied.exists():
            raise BoxUnavailable("Box is already out on another loan.")

        locked.assigned_box = box
        locked.save(update_fields=["assigned_box", "updated_at"])
        scan = BoxScan.objects.create(
            makerspace=locked.makerspace,
            box=box,
            request=locked,
            actor=actor,
            context=BoxScan.Context.ISSUE,
        )
        audit.record(
            actor,
            "box.assigned",
            makerspace=locked.makerspace,
            target=locked,
            meta={"box_id": box.pk},
        )
        audit.record(
            actor,
            "box.scanned",
            makerspace=locked.makerspace,
            target=scan,
            meta={"box_id": box.pk, "request_id": locked.pk},
        )
        return locked


def issue_request(actor, request, evidence_id, remark=""):
    evidence = EvidencePhoto.objects.filter(
        pk=evidence_id,
        makerspace_id=request.makerspace_id,
        evidence_type=EvidencePhoto.EvidenceType.ISSUE,
    ).first()
    if evidence is None:
        raise RequestValidationError("Invalid issue evidence.")
    if not storage.object_exists(evidence.object_key):
        raise EvidenceNotUploaded("Issue evidence has not been uploaded.")

    with transaction.atomic():
        locked = locked_request(request)
        if locked.status != HardwareRequest.Status.ACCEPTED:
            raise InvalidTransition(
                f"Cannot issue hardware request with status {locked.status}."
            )
        if not locked.assigned_box_id or not BoxScan.objects.filter(
            request=locked,
            box_id=locked.assigned_box_id,
            context=BoxScan.Context.ISSUE,
        ).exists():
            raise RequestValidationError("Box scan required before issue.")

        availability.issue_items(locked)
        locked.issue_evidence = evidence
        locked.issue_remark = remark
        locked.issued_by = actor
        locked.issued_at = timezone.now()
        if locked.return_due_at is None:
            locked.return_due_at = locked.issued_at + timedelta(
                days=locked.makerspace.default_loan_days or 7
            )
        locked.status = HardwareRequest.Status.ISSUED
        try:
            locked.save(
                update_fields=[
                    "issue_evidence",
                    "issue_remark",
                    "issued_by",
                    "issued_at",
                    "return_due_at",
                    "status",
                    "updated_at",
                ]
            )
        except IntegrityError as exc:
            _raise_issue_conflict(exc)

        audit.record(
            actor,
            "evidence.attached",
            makerspace=locked.makerspace,
            target=evidence,
            meta={"request_id": locked.pk},
        )
        audit.record(
            actor,
            "request.issued",
            makerspace=locked.makerspace,
            target=locked,
            meta={"box_id": locked.assigned_box_id, "evidence_id": evidence.pk},
        )
        transaction.on_commit(lambda request_id=locked.pk: _notify_issued(request_id))
        return locked


def set_return_due(actor, request, return_due_at):
    with transaction.atomic():
        locked = locked_request(request)
        if locked.status not in {
            HardwareRequest.Status.ACCEPTED,
            HardwareRequest.Status.ISSUED,
            HardwareRequest.Status.PARTIALLY_RETURNED,
        }:
            raise InvalidTransition(
                f"Cannot set return due time for hardware request with status {locked.status}."
            )
        locked.return_due_at = return_due_at
        locked.return_reminder_sent_at = None
        locked.save(
            update_fields=["return_due_at", "return_reminder_sent_at", "updated_at"]
        )
        audit.record(
            actor,
            "request.return_due_updated",
            makerspace=locked.makerspace,
            target=locked,
            meta={"return_due_at": return_due_at.isoformat() if return_due_at else None},
        )
        return locked


def _raise_issue_conflict(exc):
    constraint = constraint_name(exc)
    if constraint == "uniq_active_loan_per_box":
        raise BoxUnavailable("Box is already out on another loan.") from exc
    if constraint and "issue_evidence" in constraint:
        raise RequestValidationError("Evidence already used.") from exc
    raise InvalidTransition("Could not issue request due to a conflict.") from exc


def _notify_issued(request_id):
    notifications.notify_request_issued(
        HardwareRequest.objects.select_related(
            "makerspace",
            "requester",
            "issued_by",
            "assigned_box",
        ).get(pk=request_id)
    )
