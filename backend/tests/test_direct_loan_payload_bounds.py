import pytest

from tests.test_admin_direct_loans import (
    authed,
    direct_payload,
    direct_url,
    make_admin,
    make_space,
)

pytestmark = pytest.mark.django_db


def test_direct_loan_rejects_overlong_qr_payload():
    makerspace = make_space("direct-long-qr")
    admin = make_admin(makerspace)

    response = authed(admin).post(
        direct_url(makerspace),
        direct_payload(qr_payloads=["x" * 65]),
        format="json",
    )

    assert response.status_code == 400
    assert "qr_payloads" in response.data
