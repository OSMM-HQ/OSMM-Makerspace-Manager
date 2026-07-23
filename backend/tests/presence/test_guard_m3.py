import pytest

from apps.accounts.models import User
from apps.makerspaces.models import Makerspace, MakerspaceMembership, MakerspaceRole
from apps.makerspaces.waiver_services import accept_waiver, publish_waiver
from apps.presence import services
from apps.presence.guard import (
    MemberPresenceRequired,
    PresenceRequired,
    WaiverAcceptanceRequired,
    require_active_member_presence,
)


def setup_member(space):
    user = User.objects.create_user(username="guard-member", email="guard@example.test", password="password")
    role = MakerspaceRole.objects.get(makerspace=space, slug="member")
    membership = MakerspaceMembership.objects.create(makerspace=space, user=user, assigned_role=role, role="custom")
    return user, membership


@pytest.mark.django_db
def test_guard_has_stable_membership_waiver_and_presence_contract():
    space = Makerspace.objects.create(name="Guard", slug="guard")
    user, membership = setup_member(space)
    with pytest.raises(MemberPresenceRequired) as missing:
        require_active_member_presence(User(), space)
    assert missing.value.code == "membership_required"
    waiver = publish_waiver(user, space, "Terms", "v1")
    with pytest.raises(WaiverAcceptanceRequired) as unaccepted:
        require_active_member_presence(user, space)
    assert unaccepted.value.code == "waiver_acceptance_required"
    accept_waiver(membership)
    with pytest.raises(PresenceRequired) as absent:
        require_active_member_presence(user, space)
    assert absent.value.code == "presence_required"
    services.start_session(user, space, 60)
    assert require_active_member_presence(user, space).accepted_waiver.pk == waiver.pk
