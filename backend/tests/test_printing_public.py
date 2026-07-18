import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.makerspaces.models import Makerspace
from apps.printing.models import FilamentSpool, PrintBucket, PrintRequest
from tests.test_printing import make_bucket, make_space, make_user


pytestmark = pytest.mark.django_db


def enable_printing(makerspace):
    makerspace.enabled_modules = ["printing"]
    makerspace.save(update_fields=["enabled_modules"])


def public_client():
    return APIClient()


def status_url(public_token):
    return reverse("printing:public-request-status", kwargs={"public_token": str(public_token)})


def buckets_url(makerspace):
    return reverse("printing:public-buckets", kwargs={"makerspace_slug": makerspace.slug})


def spools_url(makerspace):
    return reverse("printing:public-spools", kwargs={"makerspace_slug": makerspace.slug})


def test_public_buckets_lists_active_only():
    makerspace = make_space("public-print-buckets")
    enable_printing(makerspace)
    active = make_bucket(makerspace, name="PLA")
    make_bucket(makerspace, name="Retired", is_active=False)
    response = public_client().get(buckets_url(makerspace))
    assert response.status_code == 200
    assert [bucket["id"] for bucket in response.data] == [active.id]


def test_public_spools_are_makerspace_scoped_and_safe():
    makerspace = make_space("public-print-spools")
    other = make_space("public-print-spools-other")
    enable_printing(makerspace)
    enable_printing(other)
    spool = FilamentSpool.objects.create(
        makerspace=makerspace, material="PLA", color="white",
        initial_weight_grams=1000, remaining_weight_grams=640,
    )
    FilamentSpool.objects.create(
        makerspace=other, material="ABS", color="red",
        initial_weight_grams=1000, remaining_weight_grams=640,
    )
    response = public_client().get(spools_url(makerspace))
    assert response.status_code == 200
    assert response.data == [{"id": spool.id, "material": "PLA", "color": "white"}]


def test_token_status_hides_pii_and_has_queue_fields():
    makerspace = make_space("public-print-status")
    enable_printing(makerspace)
    request = PrintRequest.objects.create(
        bucket=PrintBucket.objects.create(makerspace=makerspace, name="Public"),
        requester=make_user("public-status-user"),
        title="Bracket",
        contact_email="hidden@example.test",
        contact_phone="hidden",
    )
    response = public_client().get(status_url(request.public_token))
    assert response.status_code == 200
    assert set(response.data) == {
        "public_token", "status", "title", "created_at", "accepted_at", "started_at",
        "completed_at", "estimated_minutes", "queue_position", "queue_approved_ahead",
        "queue_awaiting_review_ahead",
    }


def test_retired_checkin_and_email_status_routes_do_not_resolve():
    makerspace = Makerspace.objects.create(name="No legacy routes", slug="no-legacy-routes")
    assert public_client().post(f"/api/v1/public/{makerspace.slug}/checkin/verify", {}, format="json").status_code == 404
    assert public_client().post(f"/api/v1/public/{makerspace.slug}/status-by-email", {}, format="json").status_code == 404
