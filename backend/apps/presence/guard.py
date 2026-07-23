from dataclasses import dataclass

from django.utils import timezone

from apps.accounts.models import User
from apps.makerspaces.models import MakerspaceMembership, MakerspaceWaiver
from apps.presence.models import PresenceSession


class MemberPresenceRequired(Exception):
    code = "membership_required"
    default_detail = "An active membership is required."


class WaiverAcceptanceRequired(Exception):
    code = "waiver_acceptance_required"
    default_detail = "Accept the current makerspace waiver first."


class PresenceRequired(Exception):
    code = "presence_required"
    default_detail = "An active presence session is required."


@dataclass(frozen=True)
class ActiveMemberPresence:
    membership: MakerspaceMembership
    accepted_waiver: MakerspaceWaiver | None
    session: PresenceSession


def require_active_member_presence(user, makerspace):
    if not (
        user
        and user.is_authenticated
        and user.pk
        and user.is_active
        and user.access_status == User.AccessStatus.ACTIVE
    ):
        raise MemberPresenceRequired()
    membership = MakerspaceMembership.objects.filter(
        user=user, makerspace=makerspace, status="active"
    ).select_related("accepted_waiver").first()
    if membership is None:
        raise MemberPresenceRequired()
    waiver = MakerspaceWaiver.objects.filter(
        makerspace=makerspace, is_active=True
    ).first()
    if waiver and (
        membership.accepted_waiver_id != waiver.id
        or membership.waiver_version_accepted != waiver.version
    ):
        raise WaiverAcceptanceRequired()
    session = PresenceSession.objects.filter(
        member=user, makerspace=makerspace, ended_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).order_by("-started_at", "-id").first()
    if session is None:
        raise PresenceRequired()
    return ActiveMemberPresence(membership, waiver, session)
