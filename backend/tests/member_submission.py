from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.makerspaces.models import MakerspaceMembership, MakerspaceRole, MakerspaceWaiver
from apps.makerspaces.waiver_services import accept_waiver
from apps.presence import services as presence_services


def active_member_client(
    makerspace,
    username,
    *,
    display_name=None,
    email=None,
    phone="1234567890",
):
    """Create an eligible member and authenticate an API client as that member."""
    user = User.objects.create_user(
        username=username,
        password="password",
        display_name=display_name or username,
        email=email or f"{username}@example.test",
        phone=phone,
        access_status=User.AccessStatus.ACTIVE,
    )
    membership = MakerspaceMembership.objects.create(
        makerspace=makerspace,
        user=user,
        role=MakerspaceMembership.Role.CUSTOM,
        assigned_role=MakerspaceRole.objects.get(
            makerspace=makerspace,
            slug="member",
        ),
    )
    if MakerspaceWaiver.objects.filter(makerspace=makerspace, is_active=True).exists():
        accept_waiver(membership)
    presence_services.start_session(user, makerspace, 60)
    client = APIClient()
    client.force_authenticate(user)
    return user, client
