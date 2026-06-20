import pytest

from apps.printing.models import PrintRequest
from tests.test_printing import make_bucket, make_space, make_user
from tests.test_printing_public import (
    enable_printing,
    public_client,
    status_by_email_url,
    status_url,
)

pytestmark = pytest.mark.django_db


def queue_fields(data):
    return {
        "queue_position": data["queue_position"],
        "queue_approved_ahead": data["queue_approved_ahead"],
        "queue_awaiting_review_ahead": data["queue_awaiting_review_ahead"],
    }


def test_token_status_queue_position_uses_rank_model():
    makerspace = make_space("public-print-queue-rank")
    enable_printing(makerspace)
    bucket = make_bucket(makerspace)
    requester = make_user("public-print-queue-rank-requester")
    pending_first = PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Pending first",
        status=PrintRequest.Status.PENDING,
    )
    accepted_first = PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Accepted first",
        status=PrintRequest.Status.ACCEPTED,
    )
    accepted_second = PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Accepted second",
        status=PrintRequest.Status.ACCEPTED,
    )
    pending_second = PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Pending second",
        status=PrintRequest.Status.PENDING,
    )
    client = public_client()

    accepted_response = client.get(status_url(accepted_first.public_token))
    later_accepted_response = client.get(status_url(accepted_second.public_token))
    pending_response = client.get(status_url(pending_first.public_token))
    later_pending_response = client.get(status_url(pending_second.public_token))

    assert accepted_response.status_code == 200
    assert queue_fields(accepted_response.data) == {
        "queue_position": 1,
        "queue_approved_ahead": 0,
        "queue_awaiting_review_ahead": 0,
    }
    assert queue_fields(later_accepted_response.data) == {
        "queue_position": 2,
        "queue_approved_ahead": 1,
        "queue_awaiting_review_ahead": 0,
    }
    assert queue_fields(pending_response.data) == {
        "queue_position": 3,
        "queue_approved_ahead": 2,
        "queue_awaiting_review_ahead": 0,
    }
    assert queue_fields(later_pending_response.data) == {
        "queue_position": 4,
        "queue_approved_ahead": 2,
        "queue_awaiting_review_ahead": 1,
    }


@pytest.mark.parametrize(
    "request_status",
    [PrintRequest.Status.PRINTING, PrintRequest.Status.COMPLETED],
)
def test_token_status_queue_fields_null_for_non_waiting_statuses(request_status):
    makerspace = make_space(f"public-print-queue-null-{request_status}")
    enable_printing(makerspace)
    bucket = make_bucket(makerspace)
    requester = make_user(f"public-print-queue-null-{request_status}-requester")
    print_request = PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Not waiting",
        status=request_status,
    )

    response = public_client().get(status_url(print_request.public_token))

    assert response.status_code == 200
    assert queue_fields(response.data) == {
        "queue_position": None,
        "queue_approved_ahead": None,
        "queue_awaiting_review_ahead": None,
    }


def test_email_status_populates_queue_fields_for_waiting_requests():
    makerspace = make_space("public-print-queue-email")
    enable_printing(makerspace)
    bucket = make_bucket(makerspace)
    requester = make_user("public-print-queue-email-requester")
    pending = PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Pending",
        status=PrintRequest.Status.PENDING,
        contact_email="buyer@example.com",
    )
    accepted = PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Accepted",
        status=PrintRequest.Status.ACCEPTED,
        contact_email="buyer@example.com",
    )

    response = public_client().post(
        status_by_email_url(makerspace),
        {"email": "buyer@example.com"},
        format="json",
    )

    assert response.status_code == 200
    by_token = {item["public_token"]: item for item in response.data["results"]}
    assert queue_fields(by_token[str(accepted.public_token)]) == {
        "queue_position": 1,
        "queue_approved_ahead": 0,
        "queue_awaiting_review_ahead": 0,
    }
    assert queue_fields(by_token[str(pending.public_token)]) == {
        "queue_position": 2,
        "queue_approved_ahead": 1,
        "queue_awaiting_review_ahead": 0,
    }


def test_queue_position_ignores_waiting_requests_in_other_makerspaces():
    makerspace = make_space("public-print-queue-isolation")
    other_space = make_space("public-print-queue-isolation-other")
    enable_printing(makerspace)
    enable_printing(other_space)
    bucket = make_bucket(makerspace)
    other_bucket = make_bucket(other_space)
    requester = make_user("public-print-queue-isolation-requester")
    PrintRequest.objects.create(
        bucket=other_bucket,
        requester=requester,
        title="Other accepted",
        status=PrintRequest.Status.ACCEPTED,
    )
    PrintRequest.objects.create(
        bucket=other_bucket,
        requester=requester,
        title="Other pending",
        status=PrintRequest.Status.PENDING,
    )
    target = PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Target",
        status=PrintRequest.Status.PENDING,
    )

    response = public_client().get(status_url(target.public_token))

    assert response.status_code == 200
    assert queue_fields(response.data) == {
        "queue_position": 1,
        "queue_approved_ahead": 0,
        "queue_awaiting_review_ahead": 0,
    }
