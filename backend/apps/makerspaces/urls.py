from django.urls import path

from apps.makerspaces.config_views import PublicConfigView
from apps.makerspaces.views import BootstrapView
from apps.makerspaces.views_membership_invitations import InvitationClaimView, InvitationDiscoveryView
from apps.makerspaces.views_memberships import (
    MemberWaiverAcceptView, MemberWaiverView, MyMembershipsView,
    PublicMembershipRequestView,
)
from apps.makerspaces.views_member_referrals import MemberReferralView
from apps.makerspaces.member_activity_views import MemberActivityView

urlpatterns = [
    path("bootstrap", BootstrapView.as_view(), name="tenant-bootstrap"),
    path("config", PublicConfigView.as_view(), name="public-config"),
    path("public/<slug:makerspace_slug>/membership-requests", PublicMembershipRequestView.as_view(), name="public-membership-request"),
    path("memberships/me", MyMembershipsView.as_view(), name="my-memberships"),
    path("memberships/invitations", InvitationDiscoveryView.as_view(), name="membership-invitations"),
    path("memberships/invitations/<int:pk>/claim", InvitationClaimView.as_view(), name="membership-invitation-claim"),
    path("memberships/<int:pk>/accept-invitation", InvitationClaimView.as_view(), name="membership-invitation-claim-legacy"),
    path("member/makerspaces/<int:makerspace_id>/waiver", MemberWaiverView.as_view(), name="member-waiver"),
    path("member/makerspaces/<int:makerspace_id>/waiver/accept", MemberWaiverAcceptView.as_view(), name="member-waiver-accept"),
    path("member/makerspaces/<int:makerspace_id>/activity", MemberActivityView.as_view(), name="member-activity"),
    path("member/makerspaces/<int:makerspace_id>/referrals", MemberReferralView.as_view(), name="member-referrals"),
]
