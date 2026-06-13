from collections import Counter

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.boxes.models import QrScanEvent
from apps.checkin import client as checkin
from apps.hardware_requests.models import HardwareRequest, PublicToolLoan
from apps.hardware_requests.self_checkout_workflow import (
    _checkout_target,
    _issue_product,
    _issued_request,
    _locked_qr,
    _requester,
    _return_request_items,
    qr_has_active_loan,
)
from apps.hardware_requests.workflow_errors import InvalidTransition, RequestValidationError
from apps.inventory.models import InventoryAsset, InventoryProduct, TrackingMode


def issue_direct_loan(makerspace, actor, identifier, *, qr_payloads, items, due_at=None):
    result = checkin.verify(makerspace, identifier)
    with transaction.atomic():
        requester = _requester(result.external_id)
        product_quantities = Counter()
        asset_ids = []
        labels = []
        qrs = []

        seen_qr_ids = set()
        for payload in qr_payloads:
            qr = _locked_qr(makerspace, payload)
            if qr.id in seen_qr_ids:
                # Same physical QR scanned twice in one handout would decrement
                # stock twice for one item; reject before any mutation.
                raise InvalidTransition("The same QR code was scanned more than once.")
            seen_qr_ids.add(qr.id)
            if qr_has_active_loan(makerspace, qr):
                raise InvalidTransition("One scanned QR code is already checked out.")
            label, quantities, target_asset_ids = _checkout_target(qr)
            labels.append(label)
            qrs.append(qr)
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
        loan = PublicToolLoan.objects.create(
            makerspace=makerspace,
            qr_code=qrs[0] if qrs else None,
            qr_ids=[qr.id for qr in qrs],
            request=request,
            requester=requester,
            target_type="direct",
            target_id=request.id,
            target_label=", ".join(labels)[:200] or "Direct handout",
            asset_ids=asset_ids,
            source=PublicToolLoan.Source.ADMIN_DIRECT,
            due_at=due_at,
        )
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


def return_direct_loan(loan, actor):
    with transaction.atomic():
        locked = PublicToolLoan.objects.select_for_update().select_related("request").get(pk=loan.pk)
        if locked.status != PublicToolLoan.Status.CHECKED_OUT:
            raise InvalidTransition("Direct loan is not currently checked out.")
        _return_request_items(locked.request)
        if locked.asset_ids:
            InventoryAsset.objects.select_for_update().filter(
                pk__in=locked.asset_ids,
                makerspace=locked.makerspace,
            ).update(status=InventoryAsset.Status.AVAILABLE)
        locked.status = PublicToolLoan.Status.RETURNED
        locked.returned_at = timezone.now()
        locked.save(update_fields=["status", "returned_at"])
        locked.request.status = HardwareRequest.Status.RETURNED
        locked.request.closed_by = actor
        locked.request.closed_at = locked.returned_at
        locked.request.save(update_fields=["status", "closed_by", "closed_at", "updated_at"])
        _record_item_logs(actor, "admin_direct.returned", locked.makerspace, locked.request, locked)
        return locked


def _manual_product(makerspace, product_id):
    product = InventoryProduct.objects.select_for_update().filter(
        pk=product_id,
        makerspace=makerspace,
        is_public=True,
        is_archived=False,
        public_self_checkout_enabled=True,
    ).first()
    if product is None:
        raise RequestValidationError("Manual product is not enabled for direct handout.")
    if product.tracking_mode == TrackingMode.INDIVIDUAL:
        raise RequestValidationError(
            "Individual-tracked products require scanned asset QR codes for handout."
        )
    return product


def _record_item_logs(actor, action, makerspace, request, loan):
    for item in request.items.select_related("product"):
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
