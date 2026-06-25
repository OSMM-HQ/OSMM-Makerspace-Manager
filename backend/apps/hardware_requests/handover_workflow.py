from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.boxes.models import Box, BoxScan
from apps.evidence import storage
from apps.evidence.models import EvidencePhoto
from apps.hardware_requests import notifications
from apps.hardware_requests.handover_issue_helpers import (
    issue_individual_assets,
    validate_broken_rejects,
)
from apps.hardware_requests.models import HardwareRequest
from apps.hardware_requests.self_checkout_models import PublicToolLoan
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

        box = Box.objects.select_for_update().filter(
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
        if occupied.exists() or _active_public_container_loan_exists(box):
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


def issue_request(actor, request, evidence_id, remark="", asset_qr_payloads=None, rejects=None):
    asset_qr_payloads = list(asset_qr_payloads or [])
    # rejects: [{"item_id", "broken", "disposition"}] - units rejected as broken at
    # handover, either sent to the needs-fix shelf or scrapped out of inventory.
    rejects_by_item = {
        int(entry["item_id"]): (
            max(0, int(entry.get("broken", 0))),
            entry.get("disposition", availability.REJECT_NEEDS_FIX),
        )
        for entry in (rejects or [])
        if int(entry.get("broken", 0)) > 0
    }
    evidence = EvidencePhoto.objects.filter(
        pk=evidence_id,
        makerspace_id=request.makerspace_id,
        evidence_type=EvidencePhoto.EvidenceType.ISSUE,
    ).first()
    if evidence is None:
        raise RequestValidationError("Invalid issue evidence.")

    with transaction.atomic():
        locked = locked_request(request)
        if locked.status != HardwareRequest.Status.ACCEPTED:
            raise InvalidTransition(
                f"Cannot issue hardware request with status {locked.status}."
            )
        # Finalize evidence UNDER the request row lock + AFTER the status guard, so two
        # concurrent issues can't both promote the staging upload to the immutable final
        # key (the loser fails the status check before reaching here) - closes the
        # concurrent-finalizer overwrite race (Codex Stage-4 P2). PUT mode (Supabase/R2)
        # promotes staging->final + validates size; both PUT and POST then HEAD
        # size and sniff bytes to prove the immutable final object is an image.
        if settings.STORAGE_PRESIGN_METHOD == "put":
            size = storage.finalize_upload(evidence.object_key, settings.EVIDENCE_MAX_BYTES)
            if size is None:
                raise EvidenceNotUploaded("Issue evidence has not been uploaded.")
            if not (1 <= size <= settings.EVIDENCE_MAX_BYTES):
                raise RequestValidationError(
                    "Issue evidence is invalid or exceeds the size limit."
                )
        try:
            storage.validate_evidence_object(evidence.object_key)
        except storage.EvidenceObjectValidationError as exc:
            if exc.code == "missing":
                raise EvidenceNotUploaded("Issue evidence has not been uploaded.") from exc
            raise RequestValidationError(
                "Issue evidence is invalid or exceeds the size limit."
            ) from exc
        if not locked.assigned_box_id or not BoxScan.objects.filter(
            request=locked,
            box_id=locked.assigned_box_id,
            context=BoxScan.Context.ISSUE,
        ).exists():
            raise RequestValidationError("Box scan required before issue.")
        assigned_box = Box.objects.select_for_update().get(pk=locked.assigned_box_id)
        if _active_public_container_loan_exists(assigned_box):
            raise BoxUnavailable("Box is already out on another loan.")

        if rejects_by_item:
            validate_broken_rejects(locked, rejects_by_item)

        # Lock QR -> asset -> product, matching the self-checkout/direct-loan order
        # (those lock the QrCode first, then the product). Acquiring the asset/QR
        # locks before availability.issue_items() takes the InventoryProduct lock
        # avoids a lock-order inversion / deadlock across the handout flows.
        issue_individual_assets(actor, locked, asset_qr_payloads)
        availability.issue_items(locked, rejects_by_item)
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


def _active_public_container_loan_exists(box):
    return PublicToolLoan.objects.filter(
        makerspace=box.makerspace,
        container=box,
        status=PublicToolLoan.Status.CHECKED_OUT,
    ).exists()


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
