"""Email-only member notices plus matrix-controlled membership staff alerts."""

import logging

from apps.integrations.email import send_makerspace_email
from apps.integrations.notify import EmailDelivery, LifecyclePayload, notify_lifecycle
from apps.integrations.staff_notifications import staff_emails_for_feature
from apps.makerspaces.models import MakerspaceMembership, MembershipRequest

logger = logging.getLogger(__name__)


def _member_email(membership, *, event, subject, body):
    """Queue a direct member email without routing it to staff chat channels."""
    recipient = (membership.user.email or "").strip()
    if not recipient:
        return
    try:
        send_makerspace_email(
            membership.makerspace,
            subject,
            body,
            [recipient],
            stream="membership",
            event=event,
            audience="member",
        )
    except Exception:
        logger.warning(
            "membership_member_email_failed",
            extra={"makerspace_id": membership.makerspace_id, "event": event},
        )


def send_member_welcome(membership, *, source):
    event = "approved" if source == "approval" else "joined"
    _member_email(
        membership,
        event=event,
        subject=f"Welcome to {membership.makerspace.name}",
        body=f"Your membership at {membership.makerspace.name} is active. Welcome!",
    )


def send_member_verified(membership):
    _member_email(
        membership,
        event="verified",
        subject=f"You are verified at {membership.makerspace.name}",
        body=f"You have been verified as a member of {membership.makerspace.name}.",
    )


def _staff_deliveries(makerspace, subject, text, event):
    return tuple(
        EmailDelivery(
            to_email=recipient,
            subject=subject,
            text_body=text,
            audience="staff",
            stream="membership",
        )
        for recipient in staff_emails_for_feature(makerspace, "members", event=event)
    )


def notify_membership_request_pending(request, *, sync=False):
    request_id = request.pk
    makerspace = request.makerspace

    def build():
        row = MembershipRequest.objects.select_related("makerspace", "user").get(pk=request_id)
        applicant = row.user.username if row.user_id else "An applicant"
        text = f"Membership request #{row.pk} is pending. Applicant: {applicant}."
        return LifecyclePayload(
            text=text,
            emails=_staff_deliveries(
                row.makerspace,
                f"{row.makerspace.name}: membership request pending",
                text,
                "request_pending",
            ),
        )

    return notify_lifecycle(
        makerspace,
        feature="members",
        event="request_pending",
        build=build,
        sync=sync,
    )


def notify_member_joined(membership, *, sync=False):
    membership_id = membership.pk
    makerspace = membership.makerspace

    def build():
        row = MakerspaceMembership.objects.select_related("makerspace", "user").get(
            pk=membership_id
        )
        text = f"Member joined: {row.user.username}."
        return LifecyclePayload(
            text=text,
            emails=_staff_deliveries(
                row.makerspace,
                f"{row.makerspace.name}: member joined",
                text,
                "member_joined",
            ),
        )

    return notify_lifecycle(
        makerspace,
        feature="members",
        event="member_joined",
        build=build,
        sync=sync,
    )
