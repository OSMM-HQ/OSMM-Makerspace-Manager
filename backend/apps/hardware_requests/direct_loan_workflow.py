from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.boxes.models import Box, QrCode, QrScanEvent
from apps.checkin import client as checkin
from apps.evidence import storage
from apps.evidence.models import EvidencePhoto
from apps.hardware_requests.models import (
    HardwareRequest,
    PublicToolLoan,
    ReturnEvent,
)
from apps.hardware_requests.self_checkout_workflow import (
    _checkout_target,
    _issue_product,
    _issued_request,
    _requester,
    _return_request_items,
    qr_has_active_loan,
)
from apps.hardware_requests.workflow_errors import (
    EvidenceNotUploaded,
    InvalidTransition,
    RequestValidationError,
    ReturnValidationError,
)
from apps.inventory.models import InventoryAsset, InventoryProduct, TrackingMode


def issue_direct_loan(
    makerspace, actor, identifier, *, qr_payloads, items, container_id=None
):
    result = checkin.verify(makerspace, identifier)
    due_at = timezone.now() + timedelta(days=(makerspace.default_loan_days or 7))
    with transaction.atomic():
        if container_id is None and not qr_payloads and not items:
            raise RequestValidationError("Provide qr_payloads, items, or a container.")

        container = None
        if container_id is not None:
            container = (
                Box.objects.select_for_update()
                .filter(pk=container_id, makerspace=makerspace)
                .first()
            )
            if container is None:
                raise RequestValidationError("Container is not in this makerspace.")
            if not container.is_active:
                raise RequestValidationError("Container is not active.")
            # A physical container can only be out on one active handout at a time.
            # Explicit check gives a clean 409; the partial-unique constraint is the
            # race backstop (mirrors the per-QR active-loan guard).
            if PublicToolLoan.objects.filter(
                makerspace=makerspace,
                container=container,
                status=PublicToolLoan.Status.CHECKED_OUT,
            ).exists():
                raise InvalidTransition(
                    "That container is already out on another direct handout."
                )

        requester = _requester(result.external_id)
        product_quantities = Counter()
        asset_ids = []
        labels = []
        qrs = _locked_qrs_for_payloads(makerspace, qr_payloads)

        seen_qr_ids = set()
        for qr in qrs:
            if qr.id in seen_qr_ids:
                # Same physical QR scanned twice in one handout would decrement
                # stock twice for one item; reject before any mutation.
                raise InvalidTransition("The same QR code was scanned more than once.")
            seen_qr_ids.add(qr.id)
            if qr_has_active_loan(makerspace, qr):
                raise InvalidTransition("One scanned QR code is already checked out.")
            label, quantities, target_asset_ids = _checkout_target(
                qr, require_public=False
            )
            labels.append(label)
            product_quantities.update(quantities)
            asset_ids.extend(target_asset_ids)

        for item in items:
            product = _manual_product(makerspace, item["product_id"])
            quantity = item["quantity"]
            _issue_product(product, quantity)
            product_quantities[product] += quantity
            labels.append(product.name)

        request = _issued_request(
            makerspace,
            requester,
            result.username,
            dict(product_quantities),
            requested_for="Admin direct handout",
            issued_by=actor,
        )
        try:
            with transaction.atomic():
                loan = PublicToolLoan.objects.create(
                    makerspace=makerspace,
                    qr_code=qrs[0] if qrs else None,
                    container=container,
                    qr_ids=[qr.id for qr in qrs],
                    request=request,
                    requester=requester,
                    target_type="direct",
                    target_id=request.id,
                    target_label=", ".join(labels)[:200]
                    or (container.label if container else "Direct handout"),
                    asset_ids=asset_ids,
                    source=PublicToolLoan.Source.ADMIN_DIRECT,
                    due_at=due_at,
                )
        except IntegrityError as exc:
            raise InvalidTransition(
                "That container is already out on another direct handout."
            ) from exc
        for qr in qrs:
            QrScanEvent.objects.create(
                makerspace=makerspace,
                qr_code=qr,
                actor=actor,
                context=QrScanEvent.Context.ISSUE,
                request=request,
            )
        _record_item_logs(actor, "admin_direct.checked_out", makerspace, request, loan)
        return loan


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
        # Lock the evidence row FIRST — before finalizing the upload — so a
        # concurrent reviewed-request return can't consume/finalize the same photo
        # between our check and save. There is no single DB constraint spanning
        # PublicToolLoan.return_evidence and ReturnEvent.evidence, so this shared
        # row lock is what serializes the two return paths (incl. PUT finalize).
        EvidencePhoto.objects.select_for_update().get(pk=evidence.pk)
        # One return photo per handover. A RETURN photo must not already back
        # another direct-loan return OR a reviewed-request ReturnEvent (both are
        # single-use). The PublicToolLoan OneToOne is the race-proof backstop for
        # the direct-loan side; ReturnEvent.evidence is its own OneToOne.
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
            # Concurrent return reusing the same evidence lost the unique race.
            raise ReturnValidationError("Evidence already used.") from exc
        locked.request.status = HardwareRequest.Status.RETURNED
        locked.request.closed_by = actor
        locked.request.closed_at = locked.returned_at
        locked.request.save(
            update_fields=["status", "closed_by", "closed_at", "updated_at"]
        )
        _record_item_logs(
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
        size = storage.finalize_upload(
            evidence.object_key, settings.EVIDENCE_MAX_BYTES
        )
        if size is None:
            raise EvidenceNotUploaded("Return evidence has not been uploaded.")
        if not (1 <= size <= settings.EVIDENCE_MAX_BYTES):
            raise ReturnValidationError(
                "Return evidence is invalid or exceeds the size limit."
            )
    elif not storage.object_exists(evidence.object_key):
        raise EvidenceNotUploaded("Return evidence has not been uploaded.")


def _locked_qrs_for_payloads(makerspace, payloads):
    if not payloads:
        return []

    unique_payloads = set(payloads)
    qrs_by_payload = {
        qr.payload: qr
        for qr in QrCode.objects.select_for_update()
        .filter(
            payload__in=unique_payloads,
            makerspace=makerspace,
            status=QrCode.Status.ACTIVE,
        )
        .order_by("pk")
    }
    if len(qrs_by_payload) != len(unique_payloads):
        raise RequestValidationError("QR code is not active for this makerspace.")
    return [qrs_by_payload[payload] for payload in payloads]


def _manual_product(makerspace, product_id):
    product = InventoryProduct.objects.select_for_update().filter(
        pk=product_id,
        makerspace=makerspace,
        is_archived=False,
    ).first()
    if product is None:
        raise RequestValidationError(
            "Manual product is not in this makerspace or is archived."
        )
    if product.tracking_mode == TrackingMode.INDIVIDUAL:
        raise RequestValidationError(
            "Individual-tracked products require scanned asset QR codes for handout."
        )
    return product


def _record_item_logs(actor, action, makerspace, request, loan):
    items = list(request.items.select_related("product"))
    if not items and loan.container_id:
        audit.record(
            actor,
            action,
            makerspace=makerspace,
            target=loan.container,
            meta={
                "loan_id": loan.id,
                "request_id": request.id,
                "container_id": loan.container_id,
                "source": loan.source,
            },
        )
        return

    for item in items:
        audit.record(
            actor,
            action,
            makerspace=makerspace,
            target=item.product,
            meta={
                "loan_id": loan.id,
                "request_id": request.id,
                "product_id": item.product_id,
                "quantity": item.issued_quantity,
                "source": loan.source,
            },
        )
