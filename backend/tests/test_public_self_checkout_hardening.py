import pytest
from django.test import override_settings

from apps.hardware_requests.models import PublicToolLoan
from apps.hardware_requests.self_checkout_views import (
    PublicToolCheckoutView,
    PublicToolReturnView,
)
from tests.test_public_self_checkout import (
    api_client,
    checkout_payload,
    checkout_url,
    make_product,
    make_qr,
    make_space,
)

pytestmark = pytest.mark.django_db


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_public_checkout_response_omits_physical_target_labels():
    makerspace = make_space("checkout-public-shape")
    product = make_product(
        makerspace,
        name="Public Multimeter",
        public_self_checkout_enabled=True,
    )
    qr = make_qr(makerspace, product)

    response = api_client().post(
        checkout_url(makerspace),
        checkout_payload(qr.payload),
        format="json",
    )

    assert response.status_code == 201
    assert response.data["status"] == PublicToolLoan.Status.CHECKED_OUT
    assert response.data["items"] == [{"product_name": product.name, "quantity": 1}]
    assert "target_type" not in response.data
    assert "target_label" not in response.data


@override_settings(API_CLIENT_AUTH_REQUIRED=False)
def test_public_checkout_rejects_overlong_qr_payload():
    makerspace = make_space("checkout-long-payload")

    response = api_client().post(
        checkout_url(makerspace),
        checkout_payload("x" * 65),
        format="json",
    )

    assert response.status_code == 400
    assert "payload" in response.data


def test_public_self_checkout_views_use_dedicated_throttle_scopes():
    assert PublicToolCheckoutView.throttle_scope == "public_tool_checkout"
    assert PublicToolReturnView.throttle_scope == "public_tool_return"
