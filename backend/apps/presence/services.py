from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit import services as audit
from apps.makerspaces.models import MakerspaceMembership, presence_presets
from apps.presence.geofence import evaluate_geofence, geofence_metadata
from apps.presence.guard import MemberPresenceRequired
from apps.presence.models import PresenceSession


def _active_sessions(user, makerspace, now):
    return PresenceSession.objects.select_for_update().filter(
        member=user,
        makerspace=makerspace,
        ended_at__isnull=True,
        expires_at__gt=now,
    ).order_by("-started_at", "-id")


def start_session(user, makerspace, duration_minutes, *, latitude=None, longitude=None, accuracy=None):
    if duration_minutes not in presence_presets(makerspace):
        raise ValidationError({"duration_minutes": "Choose an allowed session length."})
    # ADVISORY by design (owner decision): browser-supplied coordinates are spoofable, so the geofence
    # is recorded for staff visibility but NEVER blocks a session. Do not convert this into a hard gate.
    geofence_result = evaluate_geofence(makerspace, latitude=latitude, longitude=longitude, accuracy=accuracy)
    with transaction.atomic():
        membership = MakerspaceMembership.objects.select_for_update().filter(
            makerspace=makerspace, user=user, status="active"
        ).first()
        if membership is None:
            raise MemberPresenceRequired()
        now = timezone.now()
        requested_duration = timedelta(minutes=duration_minutes)
        requested_expiry = now + requested_duration
        active = list(_active_sessions(user, makerspace, now))
        if active and active[0].expires_at - active[0].started_at == requested_duration:
            return active[0]
        for session in active:
            session.ended_at = now
            session.ended_by = user
            session.end_reason = PresenceSession.EndReason.SUPERSEDED
            session.save(update_fields=["ended_at", "ended_by", "end_reason"])
            audit.record(user, "presence.superseded", makerspace=makerspace, target=session)
        session = PresenceSession.objects.create(
            member=user,
            makerspace=makerspace,
            membership=membership,
            started_at=now,
            expires_at=requested_expiry,
        )
        audit.record(user, "presence.started", makerspace=makerspace, target=session, meta=geofence_metadata(geofence_result))
        return session


def current_session(user, makerspace):
    return PresenceSession.objects.filter(
        member=user, makerspace=makerspace, ended_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).order_by("-started_at", "-id").first()


def end_session(user, makerspace):
    with transaction.atomic():
        session = _active_sessions(user, makerspace, timezone.now()).first()
        if session is None:
            return None
        session.ended_at = timezone.now()
        session.ended_by = user
        session.end_reason = PresenceSession.EndReason.USER_ENDED
        session.save(update_fields=["ended_at", "ended_by", "end_reason"])
        audit.record(user, "presence.ended", makerspace=makerspace, target=session)
        return session


def end_sessions_for_membership(actor, membership, reason="membership_revoked"):
    now = timezone.now()
    for session in _active_sessions(membership.user, membership.makerspace, now):
        session.ended_at = now
        session.ended_by = actor
        session.end_reason = reason
        session.save(update_fields=["ended_at", "ended_by", "end_reason"])
        audit.record(actor, "presence.ended_membership_revoked", makerspace=membership.makerspace, target=session)
