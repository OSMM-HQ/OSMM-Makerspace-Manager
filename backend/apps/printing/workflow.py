from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.printing.emails import send_print_email
from apps.printing.models import PrintRequest


class InvalidTransition(Exception):
    pass


_ALLOWED = {
    PrintRequest.Status.PENDING: {
        PrintRequest.Status.ACCEPTED,
        PrintRequest.Status.REJECTED,
    },
    PrintRequest.Status.ACCEPTED: {PrintRequest.Status.PRINTING},
    PrintRequest.Status.PRINTING: {
        PrintRequest.Status.COMPLETED,
        PrintRequest.Status.FAILED,
    },
}


def _transition(print_request, actor, status, event, reason=""):
    with transaction.atomic():
        locked = (
            PrintRequest.objects.select_for_update()
            .select_related("bucket__makerspace", "requester")
            .get(pk=print_request.pk)
        )
        if status not in _ALLOWED.get(locked.status, set()):
            raise InvalidTransition(
                f"Cannot transition print request from {locked.status} to {status}."
            )

        locked.status = status
        locked.handled_by = actor
        if status == PrintRequest.Status.ACCEPTED:
            locked.accepted_at = timezone.now()
        if status == PrintRequest.Status.COMPLETED:
            locked.completed_at = timezone.now()
        if status in (PrintRequest.Status.REJECTED, PrintRequest.Status.FAILED):
            locked.reason = reason

        locked.save(
            update_fields=[
                "status",
                "handled_by",
                "accepted_at",
                "completed_at",
                "reason",
                "updated_at",
            ]
        )
        audit.record(
            actor,
            f"print.{event}",
            makerspace=locked.bucket.makerspace,
            target=locked,
        )
        if event in {"accepted", "rejected", "completed"}:
            transaction.on_commit(
                lambda request_id=locked.pk, email_event=event: send_print_email(
                    email_event,
                    PrintRequest.objects.select_related(
                        "bucket__makerspace", "requester"
                    ).get(pk=request_id),
                )
            )
        return locked


def accept(print_request, actor):
    return _transition(
        print_request,
        actor,
        PrintRequest.Status.ACCEPTED,
        "accepted",
    )


def reject(print_request, actor, reason):
    return _transition(
        print_request,
        actor,
        PrintRequest.Status.REJECTED,
        "rejected",
        reason=reason,
    )


def start(print_request, actor):
    return _transition(
        print_request,
        actor,
        PrintRequest.Status.PRINTING,
        "started",
    )


def complete(print_request, actor):
    return _transition(
        print_request,
        actor,
        PrintRequest.Status.COMPLETED,
        "completed",
    )


def fail(print_request, actor, reason):
    return _transition(
        print_request,
        actor,
        PrintRequest.Status.FAILED,
        "failed",
        reason=reason,
    )
