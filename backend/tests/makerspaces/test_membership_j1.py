from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.makerspaces import limits, membership_services
from apps.makerspaces.models import Makerspace, MakerspaceMembership, MakerspaceRole, MembershipRequest


def user(name, verified=True):
    item = User.objects.create_user(username=name, email=f"{name}@example.test", password="password")
    if verified:
        item.email_verified_at = timezone.now()
        item.save(update_fields=["email_verified_at"])
    return item


def space(slug, **kwargs):
    return Makerspace.objects.create(name=slug.title(), slug=slug, **kwargs)


def member_role(makerspace):
    return MakerspaceRole.objects.get(makerspace=makerspace, slug="member")


def manager(makerspace, name="manager"):
    actor = user(name)
    MakerspaceMembership.objects.create(
        makerspace=makerspace,
        user=actor,
        assigned_role=MakerspaceRole.objects.get(makerspace=makerspace, slug="space_manager"),
        role=MakerspaceMembership.Role.SPACE_MANAGER,
    )
    return actor


pytestmark = pytest.mark.django_db(transaction=True)


def test_join_policies_default_request_and_open_reactivation():
    applicant = user("policy-applicant")
    requested = space("policy-request")
    outcome = membership_services.request_membership(applicant, requested)
    assert outcome == {"outcome": "requested", "request_id": outcome.id, "state": "requested"}

    invite_only = space("policy-invite", membership_policy=Makerspace.MembershipPolicy.INVITE_ONLY)
    with pytest.raises(ValidationError, match="invite-only"):
        membership_services.request_membership(applicant, invite_only)

    stale_open = space("policy-stale", membership_policy=Makerspace.MembershipPolicy.OPEN)
    Makerspace.objects.filter(pk=stale_open.pk).update(
        membership_policy=Makerspace.MembershipPolicy.INVITE_ONLY
    )
    with pytest.raises(ValidationError, match="invite-only"):
        membership_services.request_membership(user("policy-stale-applicant"), stale_open)

    open_space = space("policy-open", membership_policy=Makerspace.MembershipPolicy.OPEN)
    old = MembershipRequest.objects.create(
        makerspace=open_space, user=applicant, invite_email=applicant.email,
        kind=MembershipRequest.Kind.REQUEST, state=MembershipRequest.State.REQUESTED,
    )
    joined = membership_services.request_membership(applicant, open_space)
    membership = MakerspaceMembership.objects.get(pk=joined.id)
    old.refresh_from_db()
    assert joined["outcome"] == "joined"
    assert membership.status == old.state == MembershipRequest.State.ACTIVE
    membership.status = "revoked"
    membership.save(update_fields=["status"])
    rejoined = membership_services.request_membership(applicant, open_space)
    assert rejoined.id == membership.id
    assert MakerspaceMembership.objects.filter(makerspace=open_space, user=applicant).count() == 1


def test_referral_is_member_only_non_escalating_and_claim_requires_verified_email():
    makerspace = space("referrals", referrals_enabled=True)
    referrer = user("referrer")
    referrer_membership = MakerspaceMembership.objects.create(
        makerspace=makerspace, user=referrer, assigned_role=member_role(makerspace), role="custom"
    )
    with pytest.raises(PermissionDenied):
        membership_services.refer_membership(user("outsider"), makerspace, "x@example.test")
    referral = membership_services.refer_membership(referrer, makerspace, "invitee@example.test")
    assert referral.auto_activate_on_claim is True
    assert referral.assigned_role == member_role(makerspace)
    assert referral.assigned_role.granted_actions == []
    membership_services.set_can_refer(manager(makerspace), referrer_membership, False)
    with pytest.raises(PermissionDenied):
        membership_services.refer_membership(referrer, makerspace, "other@example.test")

    invitee = user("invitee", verified=False)
    with pytest.raises(ValidationError, match="verified email"):
        membership_services.claim_invitation(invitee, referral.id)
    invitee.email_verified_at = timezone.now()
    invitee.save(update_fields=["email_verified_at"])
    joined = membership_services.claim_invitation(invitee, referral.id)
    referral.refresh_from_db()
    assert joined.status == "active"
    assert joined.assigned_role == member_role(makerspace)
    assert referral.state == MembershipRequest.State.ACTIVE and referral.decided_at is not None


def test_manager_invitation_claim_remains_approval_gated_and_unverified_escape_hatch():
    makerspace = space("manager-invites")
    actor = manager(makerspace)
    invitee = user("manager-invitee")
    invite = membership_services.invite_membership(actor, makerspace, invitee.email, member_role(makerspace))
    claimed = membership_services.claim_invitation(invitee, invite.id)
    assert claimed.state == MembershipRequest.State.INVITED
    assert membership_services.approve_request(actor, claimed, member_role(makerspace)).status == "active"

    unverified = user("manual-invitee", verified=False)
    manual = membership_services.invite_membership(actor, makerspace, unverified.email, member_role(makerspace))
    assert membership_services.approve_request(actor, manual, member_role(makerspace)).user_id == unverified.id


def test_capability_toggles_verification_scope_revocation_and_audit():
    first, second = space("verification-a"), space("verification-b")
    actor = manager(first)
    target = user("verification-target")
    target_membership = MakerspaceMembership.objects.create(
        makerspace=first, user=target, assigned_role=member_role(first), role="custom"
    )
    ordinary = user("ordinary")
    ordinary_membership = MakerspaceMembership.objects.create(
        makerspace=first, user=ordinary, assigned_role=member_role(first), role="custom"
    )
    with pytest.raises(PermissionDenied):
        membership_services.set_can_verify(ordinary, target_membership, True)
    membership_services.set_can_verify(actor, ordinary_membership, True)
    membership_services.verify_member(ordinary, target_membership)
    target_membership.refresh_from_db()
    assert target_membership.verified_by_id == ordinary.id
    with pytest.raises(PermissionDenied):
        membership_services.verify_member(ordinary, ordinary_membership)
    foreign = MakerspaceMembership.objects.create(
        makerspace=second, user=user("foreign"), assigned_role=member_role(second), role="custom"
    )
    with pytest.raises(PermissionDenied):
        membership_services.verify_member(ordinary, foreign)
    membership_services.unverify_member(actor, target_membership)
    target_membership.refresh_from_db()
    assert target_membership.verified_at is None and target_membership.verified_by is None
    membership_services.set_can_refer(actor, ordinary_membership, True)
    membership_services.revoke_membership(actor, ordinary_membership)
    ordinary_membership.refresh_from_db()
    assert not ordinary_membership.can_refer and not ordinary_membership.can_verify
    assert AuditLog.objects.filter(action__in=["membership.verified", "membership.unverified", "membership.revoked"]).count() == 3


def test_member_quota_is_charged_only_on_activation(monkeypatch):
    makerspace = space("member-quota", membership_policy=Makerspace.MembershipPolicy.OPEN,
                        resource_limit_overrides={"members": 0}, referrals_enabled=True)
    monkeypatch.setattr(limits, "is_self_host", lambda: False)
    with pytest.raises(ValidationError, match="free members limit"):
        membership_services.request_membership(user("quota-open"), makerspace)
    referrer = user("quota-referrer")
    MakerspaceMembership.objects.create(makerspace=makerspace, user=referrer,
                                        assigned_role=member_role(makerspace), role="custom")
    referral = membership_services.refer_membership(referrer, makerspace, "quota-referral@example.test")
    assert referral.pk and MakerspaceMembership.objects.filter(makerspace=makerspace).count() == 1


def test_concurrent_open_join_is_idempotent_and_audits_once():
    makerspace = space("concurrent-join", membership_policy=Makerspace.MembershipPolicy.OPEN)
    applicant = user("concurrent-applicant")
    gate = Barrier(2)

    def join():
        close_old_connections()
        try:
            gate.wait(timeout=5)
            return membership_services.request_membership(
                User.objects.get(pk=applicant.pk), Makerspace.objects.get(pk=makerspace.pk)
            )["membership_id"]
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert len(set(pool.map(lambda _: join(), range(2)))) == 1
    assert MakerspaceMembership.objects.filter(makerspace=makerspace, user=applicant, status="active").count() == 1
    assert AuditLog.objects.filter(makerspace=makerspace, action="membership.joined").count() == 1
