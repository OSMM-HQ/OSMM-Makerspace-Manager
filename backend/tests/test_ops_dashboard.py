from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.hardware_requests.models import HardwareRequest, PublicProblemReport, PublicToolLoan
from apps.integrations.models import EmailLog
from apps.makerspaces.models import MakerspaceMembership
from apps.operations import views_dashboard
from apps.operations.models import StocktakeSession
from apps.printing.models import PrintBucket, PrintRequest
from tests.return_helpers import authenticated_client, make_member, make_product, make_space, make_user

pytestmark = pytest.mark.django_db


def dashboard_url(makerspace):
    return f"/api/v1/admin/makerspace/{makerspace.id}/dashboard"


def test_space_manager_gets_dashboard_with_all_count_keys():
    makerspace = make_space("ops-dashboard-access")
    manager = make_member("ops-dashboard-manager", makerspace)

    response = authenticated_client(manager).get(dashboard_url(makerspace))

    assert response.status_code == 200
    assert set(response.data) == set(views_dashboard.DashboardSerializer().fields)
    assert all(isinstance(value, int) for value in response.data.values())


def test_dashboard_rejects_guest_non_member_and_archived_makerspace():
    makerspace = make_space("ops-dashboard-rbac")
    other = make_space("ops-dashboard-other")
    archived = make_space("ops-dashboard-archived")
    archived.archived_at = timezone.now()
    archived.save(update_fields=["archived_at"])
    guest = make_member(
        "ops-dashboard-guest",
        makerspace,
        membership_role=MakerspaceMembership.Role.GUEST_ADMIN,
        role=User.Role.GUEST_ADMIN,
    )
    non_member = make_user("ops-dashboard-non-member", access_status=User.AccessStatus.ACTIVE)
    archived_manager = make_member("ops-dashboard-archived-manager", archived)

    assert authenticated_client(guest).get(dashboard_url(makerspace)).status_code == 403
    assert authenticated_client(non_member).get(dashboard_url(makerspace)).status_code == 404
    assert authenticated_client(archived_manager).get(dashboard_url(archived)).status_code == 404
    assert authenticated_client(make_member("ops-dashboard-other-manager", other)).get(
        dashboard_url(makerspace)
    ).status_code == 404


def test_dashboard_counts_are_tenant_scoped_and_count_only_categories():
    makerspace = make_space("ops-dashboard-counts")
    other = make_space("ops-dashboard-counts-other")
    manager = make_member("ops-dashboard-counts-manager", makerspace)
    requester = make_user("ops-dashboard-counts-requester", access_status=User.AccessStatus.ACTIVE)
    other_requester = make_user("ops-dashboard-counts-other-requester", access_status=User.AccessStatus.ACTIVE)
    now = timezone.now()

    HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        status=HardwareRequest.Status.PENDING_APPROVAL,
    )
    HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        status=HardwareRequest.Status.ACCEPTED,
    )
    HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        status=HardwareRequest.Status.ISSUED,
        return_due_at=now - timedelta(days=1),
    )
    make_product(makerspace, name="Out of stock", available_quantity=0)
    problem_product = make_product(makerspace, name="Problem tool")
    problem_request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        status=HardwareRequest.Status.RETURNED,
    )
    problem_loan = PublicToolLoan.objects.create(
        makerspace=makerspace,
        request=problem_request,
        requester=requester,
        target_type="product",
        target_id=problem_product.id,
        target_label=problem_product.name,
        status=PublicToolLoan.Status.RETURNED,
        returned_at=now,
    )
    PublicProblemReport.objects.create(
        makerspace=makerspace,
        loan=problem_loan,
        request=problem_request,
        requester=requester,
        note="It was not working.",
    )
    direct_request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        status=HardwareRequest.Status.ISSUED,
    )
    PublicToolLoan.objects.create(
        makerspace=makerspace,
        request=direct_request,
        requester=requester,
        target_type="product",
        target_id=problem_product.id,
        target_label=problem_product.name,
        due_at=now - timedelta(days=1),
        returned_at=None,
    )
    StocktakeSession.objects.create(
        makerspace=makerspace,
        status=StocktakeSession.Status.COMPLETED,
        started_by=manager,
    )
    EmailLog.objects.create(
        makerspace=makerspace,
        to_email="borrower@example.com",
        subject="Failed",
        status=EmailLog.Status.FAILED,
    )
    bucket = PrintBucket.objects.create(makerspace=makerspace, name="General")
    PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Queued print",
        status=PrintRequest.Status.PENDING,
    )
    PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Running print",
        status=PrintRequest.Status.PRINTING,
    )
    PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Finished print",
        status=PrintRequest.Status.COMPLETED,
    )

    HardwareRequest.objects.create(
        makerspace=other,
        requester=other_requester,
        requester_username=other_requester.username,
        status=HardwareRequest.Status.PENDING_APPROVAL,
    )
    make_product(other, name="Other out of stock", available_quantity=0)
    StocktakeSession.objects.create(
        makerspace=other,
        status=StocktakeSession.Status.COMPLETED,
    )
    EmailLog.objects.create(
        makerspace=other,
        to_email="other@example.com",
        subject="Failed",
        status=EmailLog.Status.FAILED,
    )

    response = authenticated_client(manager).get(dashboard_url(makerspace))

    assert response.status_code == 200
    assert response.data["pending_requests"] == 1
    assert response.data["awaiting_issue"] == 1
    assert response.data["overdue_loans"] == 2
    assert response.data["open_problem_reports"] == 1
    assert response.data["low_stock"] == 1
    assert response.data["stocktakes_awaiting_approval"] == 1
    assert response.data["failed_emails"] == 1
    assert response.data["pending_prints"] == 1
    assert response.data["active_prints"] == 1
    assert response.data["prints_awaiting_collection"] == 1


def test_build_dashboard_is_fail_safe(monkeypatch):
    makerspace = make_space("ops-dashboard-fail-safe")

    class BrokenManager:
        def filter(self, *args, **kwargs):
            raise RuntimeError("database unavailable")

    class BrokenHardwareRequest:
        objects = BrokenManager()

        class Status:
            ISSUED = "issued"
            PARTIALLY_RETURNED = "partially_returned"
            PENDING_APPROVAL = "pending_approval"
            ACCEPTED = "accepted"

    monkeypatch.setattr(views_dashboard, "HardwareRequest", BrokenHardwareRequest)

    counts = views_dashboard.build_dashboard(makerspace)

    assert set(counts) == set(views_dashboard.DashboardSerializer().fields)
    assert counts["overdue_loans"] == 0
    assert counts["pending_requests"] == 0
    assert counts["awaiting_issue"] == 0