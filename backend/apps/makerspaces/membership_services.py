"""Audited, locked lifecycle changes for makerspace memberships."""

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts import rbac
from apps.accounts.models import User
from apps.audit import services as audit
from apps.makerspaces import limits, role_services
from apps.makerspaces.models import (
    Makerspace,
    MakerspaceMembership,
    MakerspaceRole,
    MembershipRequest,
)


def normalized_email(value):
    return (value or "").strip().lower()


def _eligible_user(user):
    """Self-service join eligibility: active account with a verified email."""
    return bool(user and user.is_active and user.email_verified_at and user.email)


def _approvable_user(user):
    """Manager-approval eligibility: an active account is enough. Email need NOT be
    verified — this is the self-host / no-platform-SMTP escape hatch where a manager
    manually activates a member who could never receive an OTP."""
    return bool(user and user.is_active and user.email)


def request_membership(user, makerspace):
    if not _eligible_user(user):
        raise ValidationError({"detail": "An active account with a verified email is required."})
    with transaction.atomic():
        makerspace = Makerspace.objects.select_for_update().get(pk=makerspace.pk)
        if MakerspaceMembership.objects.select_for_update().filter(
            makerspace=makerspace, user=user, status="active"
        ).exists():
            raise ValidationError({"detail": "You are already an active member."})
        try:
            request = MembershipRequest.objects.create(
                makerspace=makerspace, user=user, invite_email=normalized_email(user.email),
                kind=MembershipRequest.Kind.REQUEST, state=MembershipRequest.State.REQUESTED,
                requested_by=user,
            )
        except IntegrityError as exc:
            raise ValidationError({"detail": "An open membership request already exists."}, code="conflict") from exc
        audit.record(user, "membership.requested", makerspace=makerspace, target=request)
        return request


def invite_membership(actor, makerspace, invite_email, assigned_role):
    email = normalized_email(invite_email)
    if not email:
        raise ValidationError({"invite_email": "An email address is required."})
    with transaction.atomic():
        makerspace = Makerspace.objects.select_for_update().get(pk=makerspace.pk)
        role = MakerspaceRole.objects.select_for_update().get(pk=assigned_role.pk)
        if role.makerspace_id != makerspace.id:
            raise ValidationError({"role_id": "Role must belong to this makerspace."})
        role_services.can_assign_role(actor, makerspace, role)
        user = User.objects.filter(email__iexact=email).first()
        try:
            request = MembershipRequest.objects.create(
                makerspace=makerspace, user=user, invite_email=email,
                kind=MembershipRequest.Kind.INVITE, state=MembershipRequest.State.INVITED,
                invited_by=actor, assigned_role=role,
            )
        except IntegrityError as exc:
            raise ValidationError({"detail": "An open invitation already exists."}, code="conflict") from exc
        audit.record(actor, "membership.invited", makerspace=makerspace, target=request,
                     meta={"role_id": role.id, "invite_email": email})
    from apps.integrations.email import send_makerspace_email
    send_makerspace_email(makerspace, "Makerspace membership invitation",
                          "You have been invited to join this makerspace. Sign in with this email to claim the invitation.",
                          [email], stream="membership", event="invitation", audience="member")
    return request


def claim_invitation(user, request_id):
    email = normalized_email(user.email)
    with transaction.atomic():
        request = MembershipRequest.objects.select_for_update().select_related("makerspace").filter(pk=request_id).first()
        if request is None:
            raise ValidationError({"detail": "Invitation not found."})
        if request.kind != MembershipRequest.Kind.INVITE or request.state != MembershipRequest.State.INVITED:
            raise ValidationError({"detail": "Invitation is not claimable."})
        if not email or request.invite_email != email:
            raise PermissionDenied()
        request.user = user
        request.save(update_fields=["user", "updated_at"])
        audit.record(user, "membership.invitation_claimed", makerspace=request.makerspace, target=request)
        return request


def approve_request(actor, request, assigned_role):
    with transaction.atomic():
        makerspace = Makerspace.objects.select_for_update().get(pk=request.makerspace_id)
        request = MembershipRequest.objects.select_for_update(of=("self",)).get(pk=request.pk)
        target_user = User.objects.select_for_update().filter(pk=request.user_id).first()
        request.user = target_user
        if request.state not in (MembershipRequest.State.REQUESTED, MembershipRequest.State.INVITED):
            raise ValidationError({"detail": "This membership request is no longer open."})
        if not _approvable_user(request.user):
            raise ValidationError({"detail": "The invited member needs an active account."})
        role = MakerspaceRole.objects.select_for_update().get(pk=assigned_role.pk)
        if role.makerspace_id != makerspace.id:
            raise ValidationError({"role_id": "Role must belong to this makerspace."})
        membership = MakerspaceMembership.objects.select_for_update().filter(
            makerspace=makerspace, user=request.user
        ).first()
        role_services.can_assign_role(actor, makerspace, role, target_membership=membership)
        adding = membership is None or membership.status != "active"
        if adding:
            limits.check_quota(makerspace, "members", adding=1)
        now = timezone.now()
        if membership is None:
            membership = MakerspaceMembership.objects.create(
                makerspace=makerspace, user=request.user, assigned_role=role,
                role=role.legacy_role or MakerspaceMembership.Role.CUSTOM,
                status="active", activated_at=now, activated_by=actor,
            )
        else:
            membership.assigned_role = role
            membership.role = role.legacy_role or MakerspaceMembership.Role.CUSTOM
            membership.status = "active"
            membership.activated_at = now
            membership.activated_by = actor
            membership.revoked_at = None
            membership.revoked_by = None
            membership.revocation_reason = ""
            membership.save()
        request.assigned_role = role
        request.state = MembershipRequest.State.ACTIVE
        request.decided_by = actor
        request.decided_at = now
        request.save(update_fields=["assigned_role", "state", "decided_by", "decided_at", "updated_at"])
        audit.record(actor, "membership.approved", makerspace=makerspace, target=membership,
                     meta={"request_id": request.id, "role_id": role.id})
        audit.record(actor, "membership.role_changed", makerspace=makerspace, target=membership,
                     meta={"role_id": role.id})
        return membership


def revoke_membership(actor, membership, reason=""):
    with transaction.atomic():
        makerspace = Makerspace.objects.select_for_update().get(pk=membership.makerspace_id)
        membership = MakerspaceMembership.objects.select_for_update().get(pk=membership.pk)
        if membership.makerspace_id != makerspace.id:
            raise PermissionDenied()
        # Non-escalation: only a global superadmin may revoke a makerspace manager
        # (a MANAGE_MAKERSPACE holder). Otherwise a local Space Manager could disable a
        # peer or the owner — the same rule the legacy revoke endpoint enforces.
        actor_is_superadmin = actor.is_superuser or actor.role == User.Role.SUPERADMIN
        if not actor_is_superadmin and rbac.Action.MANAGE_MAKERSPACE in rbac.actions_for_membership(membership):
            raise PermissionDenied("Only a superadmin can revoke a makerspace manager.")
        if membership.status != "revoked":
            membership.status = "revoked"
            membership.revoked_at = timezone.now()
            membership.revoked_by = actor
            membership.revocation_reason = reason or ""
            membership.save(update_fields=["status", "revoked_at", "revoked_by", "revocation_reason"])
            audit.record(actor, "membership.revoked", makerspace=makerspace, target=membership,
                         meta={"reason": membership.revocation_reason})
        # M3 seam: end active presence here once the presence domain exists.
        from apps.presence.services import end_sessions_for_membership

        end_sessions_for_membership(actor, membership)
        MembershipRequest.objects.filter(makerspace=makerspace, user=membership.user,
                                         state__in=["requested", "invited"]).update(
            state=MembershipRequest.State.REVOKED, decided_by=actor, decided_at=timezone.now()
        )
        return membership


def revoke_request(actor, request, reason=""):
    with transaction.atomic():
        request = MembershipRequest.objects.select_for_update().select_related("makerspace").get(pk=request.pk)
        if request.state == MembershipRequest.State.ACTIVE and request.user_id:
            membership = MakerspaceMembership.objects.filter(makerspace=request.makerspace, user=request.user).first()
            if membership:
                return revoke_membership(actor, membership, reason)
        request.state = MembershipRequest.State.REVOKED
        request.decided_by = actor
        request.decided_at = timezone.now()
        request.decision_note = reason or request.decision_note
        request.save()
        audit.record(actor, "membership.revoked", makerspace=request.makerspace, target=request)
        return request


def change_role(actor, membership, assigned_role):
    if membership.status != "active":
        raise ValidationError({"detail": "Only active memberships can change role."})
    changed = role_services.assign_role(makerspace=membership.makerspace, actor=actor,
                                        membership=membership, role=assigned_role)
    audit.record(actor, "membership.role_changed", makerspace=changed.makerspace, target=changed,
                 meta={"role_id": assigned_role.id})
    return changed
