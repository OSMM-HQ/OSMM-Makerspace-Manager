import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.makerspaces.models import Makerspace, MakerspaceMembership, MakerspaceRole
from apps.makerspaces.waiver_services import accept_waiver, deactivate_waiver, publish_waiver


@pytest.mark.django_db(transaction=True)
def test_waiver_acceptance_is_versioned_and_no_waiver_is_noop():
    space = Makerspace.objects.create(name="Waiver", slug="waiver")
    actor = User.objects.create_user(username="waiver-admin", email="admin@example.test", password="password", is_superuser=True)
    member_user = User.objects.create_user(username="waiver-member", email="member@example.test", password="password")
    role = MakerspaceRole.objects.get(makerspace=space, slug="member")
    membership = MakerspaceMembership.objects.create(makerspace=space, user=member_user, assigned_role=role, role="custom")
    unchanged, waiver = accept_waiver(membership)
    assert waiver is None and unchanged.waiver_accepted_at is None
    first = publish_waiver(actor, space, "First terms", "v1")
    accepted, current = accept_waiver(membership)
    assert current.pk == first.pk and accepted.waiver_version_accepted == "v1"
    second = publish_waiver(actor, space, "Second terms", "v2")
    accepted.refresh_from_db()
    assert accepted.waiver_version_accepted != second.version
    deactivate_waiver(actor, space)
    assert accept_waiver(accepted)[1] is None


@pytest.mark.django_db(transaction=True)
def test_revoked_member_cannot_accept_waiver():
    space = Makerspace.objects.create(name="Revoked waiver", slug="revoked-waiver")
    actor = User.objects.create_user(username="waiver-owner", email="owner@example.test", password="password", is_superuser=True)
    member_user = User.objects.create_user(username="revoked-member", email="revoked@example.test", password="password")
    role = MakerspaceRole.objects.get(makerspace=space, slug="member")
    membership = MakerspaceMembership.objects.create(makerspace=space, user=member_user, assigned_role=role, role="custom", status="revoked")
    publish_waiver(actor, space, "Terms", "v1")
    with pytest.raises(ValidationError):
        accept_waiver(membership)
