from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.evidence import storage
from apps.evidence.models import EvidencePhoto
from apps.hardware_requests.direct_loan_audit import record_item_logs
from apps.hardware_requests.models import HardwareRequest, PublicToolLoan, ReturnEvent
from apps.hardware_requests.self_checkout_workflow import _return_request_items
from apps.hardware_requests.workflow_errors import (
    EvidenceNotUploaded,
    InvalidTransition,
    RequestValidationError,
    ReturnValidationError,
)
from apps.inventory.models import InventoryAsset


def return_direct_loan(loan, actor, evidence_id, notes):
    notes = str(notes or "").strip()
    if not notes:
        raise RequestValidationError("Return notes are required.")
    evidence = EvidencePhoto.objects.filter(
        pk=evidence_id,
        makerspace_id=loan.makerspace_id,
        evidence_type=EvidencePhoto.EvidenceType.RETURN,
    ).first()
    if evidence is None:
        raise RequestValidationError("Invalid return evidence.")

    with transaction.atomic():
        locked = (
            PublicToolLoan.objects.select_for_update()
            .select_related("request")
            .get(pk=loan.pk)
        )
        if locked.status != PublicToolLoan.Status.CHECKED_OUT:
            raise InvalidTransition("Direct loan is not currently checked out.")
        EvidencePhoto.objects.select_for_update().get(pk=evidence.pk)
        if (
            PublicToolLoan.objects.filter(return_evidence=evidence).exists()
            or ReturnEvent.objects.filter(evidence=evidence).exists()
        ):
            raise ReturnValidationError("Evidence already used.")
        _validate_return_upload(evidence)
        _return_request_items(locked.request)
        if locked.asset_ids:
            InventoryAsset.objects.select_for_update().filter(
                pk__in=locked.asset_ids,
                makerspace=locked.makerspace,
            ).update(status=InventoryAsset.Status.AVAILABLE)
        locked.status = PublicToolLoan.Status.RETURNED
        locked.returned_at = timezone.now()
        locked.return_evidence = evidence
        locked.return_notes = notes
        try:
            with transaction.atomic():
                locked.save(
                    update_fields=[
                        "status",
                        "returned_at",
                        "return_evidence",
                        "return_notes",
                    ]
                )
        except IntegrityError as exc:
            raise ReturnValidationError("Evidence already used.") from exc
        locked.request.status = HardwareRequest.Status.RETURNED
        locked.request.closed_by = actor
        locked.request.closed_at = locked.returned_at
        locked.request.save(
            update_fields=["status", "closed_by", "closed_at", "updated_at"]
        )
        record_item_logs(
            actor, "admin_direct.returned", locked.makerspace, locked.request, locked
        )
        audit.record(
            actor,
            "evidence.attached",
            makerspace=locked.makerspace,
            target=evidence,
            meta={"request_id": locked.request_id},
        )
        return locked


def _validate_return_upload(evidence):
    if settings.STORAGE_PRESIGN_METHOD == "put":
        size = storage.finalize_upload(evidence.object_key, settings.EVIDENCE_MAX_BYTES)
        if size is None:
            raise EvidenceNotUploaded("Return evidence has not been uploaded.")
        if not (1 <= size <= settings.EVIDENCE_MAX_BYTES):
            raise ReturnValidationError(
                "Return evidence is invalid or exceeds the size limit."
            )
    elif not storage.object_exists(evidence.object_key):
        raise EvidenceNotUploaded("Return evidence has not been uploaded.")
