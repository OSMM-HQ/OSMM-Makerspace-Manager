import importlib.util

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.inventory.models import InventoryProduct
from apps.makerspaces.models import Makerspace
from apps.printing.models import PrintRequestFile
from tests.member_submission import active_member_client


pytestmark = pytest.mark.django_db


def test_checkin_runtime_surface_and_routes_are_retired():
    makerspace = Makerspace.objects.create(name="M7 retired", slug="m7-retired")

    assert importlib.util.find_spec("apps.checkin.client") is None
    assert "apps.checkin" not in settings.INSTALLED_APPS
    assert not any(hasattr(settings, name) for name in (
        "CHECKIN_MODE", "CHECKIN_API_URL", "CHECKIN_API_KEY", "CHECKIN_TIMEOUT",
    ))
    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    assert "checkin_verify" not in rates
    assert "staff_checkin_verify" not in rates

    client = APIClient()
    paths = (
        f"/api/v1/public/{makerspace.slug}/checkin/verify",
        f"/api/v1/admin/makerspace/{makerspace.id}/checkin/verify",
        f"/api/v1/printing/public/{makerspace.slug}/checkin/verify",
    )
    assert all(client.post(path, {}, format="json").status_code == 404 for path in paths)


def test_member_hardware_and_print_submissions_do_not_create_legacy_checkin_data():
    makerspace = Makerspace.objects.create(name="M7 member", slug="m7-member")
    product = InventoryProduct.objects.create(
        makerspace=makerspace,
        name="M7 tool",
        total_quantity=1,
        available_quantity=1,
        is_public=True,
    )
    _member, client = active_member_client(makerspace, "m7-member")
    existing_external_ids = set(
        User.objects.exclude(external_checkin_user_id="").values_list("id", flat=True)
    )
    existing_file_ids = set(
        PrintRequestFile.objects.exclude(owner_checkin_user_id="").values_list("id", flat=True)
    )

    hardware = client.post(
        f"/api/v1/public/{makerspace.slug}/requests",
        {"requested_for": "M7", "items": [{"product_id": product.id, "quantity": 1}]},
        format="json",
    )
    printing = client.post(
        f"/api/v1/printing/public/{makerspace.slug}/requests",
        {"title": "M7 print"},
        format="json",
    )

    assert hardware.status_code == 201
    assert printing.status_code == 201
    assert set(User.objects.exclude(external_checkin_user_id="").values_list("id", flat=True)) == existing_external_ids
    assert set(PrintRequestFile.objects.exclude(owner_checkin_user_id="").values_list("id", flat=True)) == existing_file_ids
    assert "checkin_" not in User.objects.filter(pk=_member.pk).values_list("username", flat=True).get()


def test_print_status_policy_no_longer_offers_checkin_verified():
    choices = Makerspace.PublicPrintStatusLookupPolicy.values

    assert "checkin_verified" not in choices
    assert Makerspace._meta.get_field("public_print_status_lookup_policy").default == "token_only"
