from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit import services as audit
from apps.checkin import client as checkin
from apps.hardware_requests import notifications
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem
from apps.hardware_requests.workflow_errors import (
    InvalidTransition,
    RequestValidationError,
    RequesterBlocked,
)
from apps.hardware_requests.workflow_utils import (
    get_or_create_requester,
    locked_request,
)
from apps.inventory import availability


def submit_request(
    makerspace,
    items,
    requested_for="",
    *,
    requester_name,
    contact_email="",
    contact_phone="",
):
    result = checkin.verify(makerspace, contact_email)

    with transaction.atomic():
        requester = get_or_create_requester(result.external_id)
        if requester.access_status != User.AccessStatus.ACTIVE:
            raise RequesterBlocked("Requester is not active.")

        request = HardwareRequest.objects.create(
            makerspace=makerspace,
            requester=requester,
            requester_username=result.username,
            requester_name=requester_name.strip(),
            requester_contact_email=contact_email.strip(),
            requester_contact_phone=contact_phone.strip(),
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
        transaction.on_commit(lambda: notifications.notify_request_submitted(request))
        return request


def accept_request(actor, request, accepted=None):
    with transaction.atomic():
        locked = locked_request(request)
        if locked.status != HardwareRequest.Status.PENDING_APPROVAL:
            raise InvalidTransition(
                f"Cannot accept hardware request with status {locked.status}."
            )

        items = list(locked.items.select_related("product").order_by("product_id"))
        total = 0
        for item in items:
            qty = (
                item.requested_quantity
                if accepted is None
                else int(accepted.get(item.pk, item.requested_quantity))
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
        transaction.on_commit(
            lambda request_id=locked.pk: notifications.notify_request_accepted(
                HardwareRequest.objects.select_related(
                    "makerspace",
                    "requester",
                    "accepted_by",
                ).get(pk=request_id)
            )
        )
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
        transaction.on_commit(
            lambda request_id=locked.pk: notifications.notify_request_rejected(
                HardwareRequest.objects.select_related(
                    "makerspace",
                    "requester",
                ).get(pk=request_id)
            )
        )
        return locked
