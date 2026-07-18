import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.makerspaces.models import Makerspace, MakerspaceMembership, MakerspaceRole
from apps.makerspaces.waiver_services import accept_waiver, publish_waiver
from apps.presence import services as presence
from apps.printing.member_activity import member_print_activity
from apps.printing.models import PrintBucket, PrintRequest, PrintRequestFile


pytestmark = pytest.mark.django_db


def member(space, name):
    user = User.objects.create_user(
        username=name,
        display_name=f"{name} display",
        email=f"{name}@example.test",
        phone="+15550000000",
    )
    role = MakerspaceRole.objects.get(makerspace=space, slug="member")
    MakerspaceMembership.objects.create(
        makerspace=space, user=user, assigned_role=role, role="custom"
    )
    return user


def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


def eligible(space, name="member"):
    user = member(space, name)
    presence.start_session(user, space, 60)
    return user


def urls(space):
    return (
        reverse("printing:public-upload-presign", kwargs={"makerspace_slug": space.slug}),
        reverse("printing:public-request-submit", kwargs={"makerspace_slug": space.slug}),
    )


def test_presign_and_submit_are_member_gated_and_snapshot_identity(monkeypatch):
    space = Makerspace.objects.create(name="M5", slug="m5")
    bucket = PrintBucket.objects.create(makerspace=space, name="Public")
    upload_url, submit_url = urls(space)
    outsider = User.objects.create_user(username="outsider")
    assert client(outsider).post(upload_url, {"kind": "stl", "filename": "a.stl"}, format="json").data["code"] == "membership_required"
    user = member(space, "waiver")
    waiver = publish_waiver(user, space, "Terms", "v1")
    assert client(user).post(submit_url, {"title": "A"}, format="json").data["code"] == "waiver_acceptance_required"
    accept_waiver(user.makerspace_memberships.get(makerspace=space))
    assert client(user).post(submit_url, {"title": "A"}, format="json").data["code"] == "presence_required"
    presence.start_session(user, space, 60)
    monkeypatch.setattr("apps.printing.public_views.presigned_print_upload", lambda *_: {"url": "https://upload"})
    upload = client(user).post(upload_url, {"kind": "stl", "filename": "a.stl"}, format="json")
    assert upload.status_code == 201
    stored = PrintRequestFile.objects.get()
    assert stored.owner == user and stored.owner_checkin_user_id is None
    response = client(user).post(submit_url, {"bucket_id": bucket.id, "title": "A", "requester_name": "forged", "contact_email": "x@x.test", "contact_phone": "x"}, format="json")
    assert response.status_code == 201
    request = PrintRequest.objects.get()
    assert (request.requester, request.requester_name, request.contact_email, request.contact_phone) == (user, user.display_name, user.email, user.phone)
    assert waiver.pk


def test_attach_is_limited_to_member_owned_uploads_and_honeypot_bypasses_guard():
    space = Makerspace.objects.create(name="M5 attach", slug="m5-attach")
    bucket = PrintBucket.objects.create(makerspace=space, name="Public")
    owner, other = eligible(space, "owner"), eligible(space, "other")
    _, submit_url = urls(space)
    foreign = PrintRequestFile.objects.create(makerspace=space, kind="stl", object_key="foreign", owner=other)
    response = client(owner).post(submit_url, {"bucket_id": bucket.id, "title": "A", "file_ids": [foreign.id]}, format="json")
    assert response.status_code == 400 and "file_ids" in response.data
    before = PrintRequest.objects.count()
    outsider = User.objects.create_user(username="bot")
    response = client(outsider).post(submit_url, {"website": "bot"}, format="json")
    assert response.status_code == 201 and PrintRequest.objects.count() == before


def test_member_activity_is_owner_safe_and_reuses_queue_projection():
    space = Makerspace.objects.create(name="M5 activity", slug="m5-activity")
    bucket = PrintBucket.objects.create(makerspace=space, name="Public")
    user, other = eligible(space, "activity"), eligible(space, "other-activity")
    own = PrintRequest.objects.create(bucket=bucket, requester=user, title="Own")
    PrintRequest.objects.create(bucket=bucket, requester=other, title="Other")
    rows = member_print_activity(space, user)
    assert [row["public_token"] for row in rows] == [str(own.public_token)]
    assert set(rows[0]) == {"public_token", "status", "title", "created_at", "accepted_at", "started_at", "completed_at", "estimated_minutes", "queue_position", "queue_approved_ahead", "queue_awaiting_review_ahead"}
