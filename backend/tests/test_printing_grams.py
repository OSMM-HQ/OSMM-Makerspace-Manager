from decimal import Decimal

import pytest

from apps.accounts.models import User
from apps.printing.models import PrintRequest
from tests.test_printing import (
    action_url,
    authenticated_client,
    make_bucket,
    make_print_manager,
    make_request,
    make_space,
    make_user,
)
from tests.test_printing_member_m5 import client as member_client, eligible, urls

pytestmark = pytest.mark.django_db


def _accept(client, print_request, **body):
    return client.post(action_url(print_request, "accept"), body, format="json")


def test_accept_sets_estimated_filament_grams():
    makerspace = make_space("grams-accept-set")
    bucket = make_bucket(makerspace)
    requester = make_user("grams-set-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("grams-set-manager", makerspace)
    print_request = make_request(bucket, requester)

    response = _accept(
        authenticated_client(manager),
        print_request,
        price="0",
        estimated_filament_grams="42.50",
    )

    assert response.status_code == 200
    print_request.refresh_from_db()
    assert print_request.estimated_filament_grams == Decimal("42.50")
    assert print_request.status == PrintRequest.Status.ACCEPTED


def test_accept_omitting_grams_preserves_requester_value():
    makerspace = make_space("grams-accept-preserve")
    bucket = make_bucket(makerspace)
    requester = make_user("grams-preserve-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("grams-preserve-manager", makerspace)
    print_request = make_request(bucket, requester)
    print_request.estimated_filament_grams = Decimal("30.00")
    print_request.save(update_fields=["estimated_filament_grams"])

    response = _accept(authenticated_client(manager), print_request, price="0")

    assert response.status_code == 200
    print_request.refresh_from_db()
    # Omitted grams must NOT zero the requester's submitted estimate.
    assert print_request.estimated_filament_grams == Decimal("30.00")


def test_accept_explicit_zero_clears_grams():
    makerspace = make_space("grams-accept-zero")
    bucket = make_bucket(makerspace)
    requester = make_user("grams-zero-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("grams-zero-manager", makerspace)
    print_request = make_request(bucket, requester)
    print_request.estimated_filament_grams = Decimal("30.00")
    print_request.save(update_fields=["estimated_filament_grams"])

    response = _accept(
        authenticated_client(manager),
        print_request,
        price="0",
        estimated_filament_grams="0",
    )

    assert response.status_code == 200
    print_request.refresh_from_db()
    assert print_request.estimated_filament_grams == Decimal("0.00")


def test_accept_negative_grams_rejected():
    makerspace = make_space("grams-accept-neg")
    bucket = make_bucket(makerspace)
    requester = make_user("grams-neg-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("grams-neg-manager", makerspace)
    print_request = make_request(bucket, requester)

    response = _accept(
        authenticated_client(manager),
        print_request,
        price="0",
        estimated_filament_grams="-5",
    )

    assert response.status_code == 400
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.PENDING


def test_public_submit_persists_estimated_grams():
    makerspace = make_space("grams-public-submit")
    bucket = make_bucket(makerspace)
    user = eligible(makerspace, "grams-public-member")
    _, submit_url = urls(makerspace)
    response = member_client(user).post(
        submit_url,
        {"bucket_id": bucket.id, "title": "Public grams", "estimated_filament_grams": "25.00"},
        format="json",
    )

    assert response.status_code == 201
    created = PrintRequest.objects.get(public_token=response.data["public_token"])
    assert created.estimated_filament_grams == Decimal("25.00")


def test_public_submit_without_grams_defaults_zero():
    makerspace = make_space("grams-public-default")
    bucket = make_bucket(makerspace)
    user = eligible(makerspace, "grams-default-member")
    _, submit_url = urls(makerspace)
    response = member_client(user).post(
        submit_url,
        {"bucket_id": bucket.id, "title": "Public default grams"},
        format="json",
    )

    assert response.status_code == 201
    created = PrintRequest.objects.get(public_token=response.data["public_token"])
    assert created.estimated_filament_grams == Decimal("0.00")
