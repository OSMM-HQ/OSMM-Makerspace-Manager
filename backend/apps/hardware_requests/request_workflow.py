from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.hardware_requests import notifications
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem
from apps.hardware_requests.workflow_errors import (
    InvalidTransition,
    RequestValidationError,
    RequesterBlocked,
)
from apps.hardware_requests.workflow_utils import locked_request
from apps.inventory import availability
from apps.notifications.emit import emit_notification


def submit_request(
    makerspace,
    items,
    requested_for="",
    *,
    requester,
):
    with transaction.atomic():
        from apps.encryption.write_fence import assert_mapped_write_allowed

        assert_mapped_write_allowed(makerspace.id)
        request = HardwareRequest.objects.create(
            makerspace=makerspace,
            requester=requester,
            requester_username=requester.username,
            requester_name=requester.display_name,
            requester_contact_email=requester.email,
            requester_contact_phone=requester.phone,
            status=HardwareRequest.Status.PENDING_APPROVAL,
            requested_for=requested_for,
        )
        HardwareRequestItem.objects.bulk_create(
            [
                HardwareRequestItem(
                    request=request,
                    product=item["product"],
                    requested_quantity=item["quantity"],
                )
                for item in items
            ]
        )
        audit.record(
            requester,
            "request.submitted",
            makerspace=makerspace,
            target=request,
        )
        notifications.notify_request_submitted(request)
        emit_notification(
            makerspace,
            level="info",
            event="request.submitted",
            title="New hardware request",
            body=f"Hardware request #{request.pk} submitted.",
        )
        return request


def accept_request(actor, request, accepted=None):
    with transaction.atomic():
        locked = locked_request(request)
        if locked.status != HardwareRequest.Status.PENDING_APPROVAL:
            raise InvalidTransition(
                f"Cannot accept hardware request with status {locked.status}."
            )

        items = list(locked.items.select_related("product").order_by("product_id"))
        if accepted is not None:
            unknown = set(accepted) - {item.pk for item in items}
            if unknown:
                raise RequestValidationError(
                    "Accepted quantities reference items that are not in this request."
                )
        total = 0
        for item in items:
            # accepted is None => accept all (full). A provided map is authoritative:
            # an item not listed is declined (0), so an empty map accepts nothing.
            qty = (
                item.requested_quantity
                if accepted is None
                else int(accepted.get(item.pk, 0))
            )
            if qty < 0 or qty > item.requested_quantity:
                raise RequestValidationError(
                    "Accepted quantity must be between 0 and the requested quantity."
                )
            item.accepted_quantity = qty
            item.save(update_fields=["accepted_quantity"])
            total += qty

        if total == 0:
            raise RequestValidationError(
                "Accept at least one unit, or reject the request instead."
            )

        # reserve_for_request now runs the individual-asset guard under its own
        # product row lock, so the check and the reservation can't race apart.
        availability.reserve_for_request(locked)

        locked.status = HardwareRequest.Status.ACCEPTED
        locked.accepted_by = actor
        locked.accepted_at = timezone.now()
        locked.save(
            update_fields=["status", "accepted_by", "accepted_at", "updated_at"]
        )
        audit.record(
            actor,
            "request.accepted",
            makerspace=locked.makerspace,
            target=locked,
            meta={"accepted": {item.pk: item.accepted_quantity for item in items}},
        )
        notifications.notify_request_accepted(locked)
        return locked


def reject_request(actor, request, reason):
    reason = str(reason or "").strip()
    if not reason:
        raise RequestValidationError("Rejection reason is required.")

    with transaction.atomic():
        locked = locked_request(request)
        if locked.status != HardwareRequest.Status.PENDING_APPROVAL:
            raise InvalidTransition(
                f"Cannot reject hardware request with status {locked.status}."
            )

        locked.status = HardwareRequest.Status.REJECTED
        locked.rejection_reason = reason
        locked.save(update_fields=["status", "rejection_reason", "updated_at"])
        audit.record(
            actor,
            "request.rejected",
            makerspace=locked.makerspace,
            target=locked,
            meta={"reason": reason},
        )
        notifications.notify_request_rejected(locked)
        return locked
