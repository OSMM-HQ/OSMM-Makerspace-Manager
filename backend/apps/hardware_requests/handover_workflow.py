from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.boxes.models import Box, BoxScan, QrCode, QrScanEvent
from apps.evidence import storage
from apps.evidence.models import EvidencePhoto
from apps.hardware_requests import notifications
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItemAsset
from apps.hardware_requests.workflow_errors import (
    BoxUnavailable,
    BoxValidationError,
    EvidenceNotUploaded,
    InvalidTransition,
    RequestValidationError,
)
from apps.hardware_requests.workflow_utils import constraint_name, locked_request
from apps.inventory import availability
from apps.inventory.models import InventoryAsset, TrackingMode


INDIVIDUAL_HANDOUT_ERROR = (
    "Individual-tracked products require scanned asset QR codes for handout."
)


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


def issue_request(actor, request, evidence_id, remark="", asset_qr_payloads=None, rejects=None):
    asset_qr_payloads = list(asset_qr_payloads or [])
    # rejects: [{"item_id", "broken", "disposition"}] — units rejected as broken at
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
    if not storage.object_exists(evidence.object_key):
        raise EvidenceNotUploaded("Issue evidence has not been uploaded.")
    if settings.STORAGE_PRESIGN_METHOD == "put":
        size = storage.object_size(evidence.object_key)
        if size is None or not (1 <= size <= settings.EVIDENCE_MAX_BYTES):
            raise RequestValidationError(
                "Issue evidence is invalid or exceeds the size limit."
            )

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

        if rejects_by_item:
            _validate_broken_rejects(locked, rejects_by_item)

        # Lock QR -> asset -> product, matching the self-checkout/direct-loan order
        # (those lock the QrCode first, then the product). Acquiring the asset/QR
        # locks before availability.issue_items() takes the InventoryProduct lock
        # avoids a lock-order inversion / deadlock across the handout flows.
        _issue_individual_assets(actor, locked, asset_qr_payloads)
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


def _validate_broken_rejects(locked, rejects_by_item):
    """Per-item broken-reject is quantity-mode only this pass: individual-tracked items
    flip specific asset rows at return, so rejecting an abstract count here would drift
    the asset statuses from the product buckets."""
    items = {item.id: item for item in locked.items.select_related("product")}
    for item_id, (broken, _disposition) in rejects_by_item.items():
        item = items.get(item_id)
        if item is None:
            raise RequestValidationError("Unknown item in broken rejects.")
        if broken > item.accepted_quantity:
            raise RequestValidationError(
                "Cannot reject more units as broken than were accepted."
            )
        if item.product.tracking_mode == TrackingMode.INDIVIDUAL:
            raise RequestValidationError(
                "Individual-tracked items can't be rejected as broken at handover; "
                "issue them and mark the specific unit damaged at return."
            )


def _issue_individual_assets(actor, locked, asset_qr_payloads):
    individual_items = list(
        locked.items.select_related("product")
        .filter(product__tracking_mode=TrackingMode.INDIVIDUAL, accepted_quantity__gt=0)
        .order_by("product_id", "pk")
    )
    expected_count = sum(item.accepted_quantity for item in individual_items)
    if expected_count == 0:
        return
    if len(asset_qr_payloads) != expected_count:
        raise RequestValidationError(INDIVIDUAL_HANDOUT_ERROR)

    seen_qr_ids = set()
    qrs_by_payload = {
        qr.payload: qr
        for qr in QrCode.objects.select_for_update()
        .filter(
            makerspace=locked.makerspace,
            payload__in=asset_qr_payloads,
            status=QrCode.Status.ACTIVE,
            target_type=QrCode.TargetType.ASSET,
        )
        .order_by("pk")
    }
    qrs = []
    for payload in asset_qr_payloads:
        qr = qrs_by_payload.get(payload)
        if qr is None:
            raise RequestValidationError(INDIVIDUAL_HANDOUT_ERROR)
        if qr.id in seen_qr_ids:
            raise InvalidTransition("The same QR code was scanned more than once.")
        seen_qr_ids.add(qr.id)
        qrs.append(qr)

    assets_by_id = {
        asset.pk: asset
        for asset in InventoryAsset.objects.select_for_update()
        .filter(
            pk__in=[qr.target_id for qr in qrs],
            makerspace=locked.makerspace,
            status=InventoryAsset.Status.AVAILABLE,
        )
        .order_by("pk")
    }
    assets_by_product = {}
    qr_by_asset_id = {}
    for qr in qrs:
        asset = assets_by_id.get(qr.target_id)
        if asset is None:
            raise RequestValidationError(INDIVIDUAL_HANDOUT_ERROR)
        assets_by_product.setdefault(asset.product_id, []).append(asset)
        qr_by_asset_id[asset.pk] = qr

    for item in individual_items:
        assets = assets_by_product.get(item.product_id, [])
        if len(assets) < item.accepted_quantity:
            raise RequestValidationError(INDIVIDUAL_HANDOUT_ERROR)
        item_assets = sorted(assets[: item.accepted_quantity], key=lambda asset: asset.pk)
        del assets[: item.accepted_quantity]
        for asset in item_assets:
            asset.status = InventoryAsset.Status.ISSUED
            asset.save(update_fields=["status", "updated_at"])
            HardwareRequestItemAsset.objects.create(
                request_item=item,
                asset=asset,
                outcome=HardwareRequestItemAsset.Outcome.ISSUED,
            )
            qr = qr_by_asset_id[asset.pk]
            QrScanEvent.objects.create(
                makerspace=locked.makerspace,
                qr_code=qr,
                request=locked,
                actor=actor,
                context=QrScanEvent.Context.ISSUE,
            )
            audit.record(
                actor,
                "asset.issued",
                makerspace=locked.makerspace,
                target=asset,
                meta={
                    "request_id": locked.pk,
                    "request_item_id": item.pk,
                    "qr_id": qr.pk,
                },
            )

    if any(assets for assets in assets_by_product.values()):
        raise RequestValidationError(INDIVIDUAL_HANDOUT_ERROR)


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
