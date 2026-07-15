import pytest
from django.contrib import admin as django_admin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, override_settings

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.makerspaces.admin_subdomains import SubdomainRequestAdmin
from apps.makerspaces.models import Makerspace, SubdomainRequest
from tests.return_helpers import make_member, make_space, make_user

pytestmark = pytest.mark.django_db


def make_superadmin(username):
    return make_user(
        username,
        role=User.Role.SUPERADMIN,
        is_staff=True,
        is_superuser=True,
    )


def make_admin_request(user):
    request = RequestFactory().post("/control/")
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


def make_pending_request(slug, label):
    makerspace = make_space(slug)
    manager = make_member(f"{slug}-manager", makerspace)
    subdomain_request = SubdomainRequest.objects.create(
        makerspace=makerspace,
        requested_label=label,
        requested_by=manager,
    )
    return makerspace, manager, subdomain_request


def run_action(action_name, subdomain_request, superadmin):
    model_admin = SubdomainRequestAdmin(SubdomainRequest, django_admin.site)
    request = make_admin_request(superadmin)
    getattr(model_admin, action_name)(
        request,
        SubdomainRequest.objects.filter(pk=subdomain_request.pk),
    )


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me")
def test_approve_provisions_platform_subdomain_and_records_decision():
    makerspace, _manager, subdomain_request = make_pending_request(
        "approval-alpha-space",
        "alpha",
    )
    superadmin = make_superadmin("approval-alpha-superadmin")

    run_action("approve_and_provision", subdomain_request, superadmin)

    makerspace.refresh_from_db()
    subdomain_request.refresh_from_db()
    assert makerspace.frontend_domain == "alpha.osmm.me"
    assert makerspace.frontend_domain_status == Makerspace.DomainStatus.VERIFIED
    assert subdomain_request.status == SubdomainRequest.Status.APPROVED
    assert subdomain_request.decided_by == superadmin
    assert subdomain_request.decided_at is not None
    assert AuditLog.objects.filter(
        actor=superadmin,
        action="makerspace.subdomain_provisioned",
        makerspace=makerspace,
        target_id=str(makerspace.pk),
    ).exists()
    assert AuditLog.objects.filter(
        actor=superadmin,
        action="makerspace.subdomain_request_approved",
        makerspace=makerspace,
        target_id=str(subdomain_request.pk),
    ).exists()


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me")
def test_approve_rolls_back_when_label_was_taken_after_request():
    makerspace, _manager, subdomain_request = make_pending_request(
        "approval-beta-requester",
        "beta",
    )
    owner = make_space("approval-beta-owner")
    owner.frontend_domain = "beta.osmm.me"
    owner.frontend_domain_status = Makerspace.DomainStatus.VERIFIED
    owner.save(
        update_fields=["frontend_domain", "frontend_domain_status", "updated_at"]
    )
    superadmin = make_superadmin("approval-beta-superadmin")

    run_action("approve_and_provision", subdomain_request, superadmin)

    makerspace.refresh_from_db()
    subdomain_request.refresh_from_db()
    assert not makerspace.frontend_domain
    assert subdomain_request.status == SubdomainRequest.Status.PENDING
    assert subdomain_request.decided_by is None
    assert subdomain_request.decided_at is None
    assert not AuditLog.objects.filter(
        action="makerspace.subdomain_request_approved",
        makerspace=makerspace,
    ).exists()


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me")
@pytest.mark.parametrize(
    "status",
    [SubdomainRequest.Status.APPROVED, SubdomainRequest.Status.REJECTED],
)
def test_approve_skips_already_decided_request(status):
    makerspace = make_space(f"approval-decided-{status}")
    manager = make_member(f"approval-decided-{status}-manager", makerspace)
    subdomain_request = SubdomainRequest.objects.create(
        makerspace=makerspace,
        requested_label=f"decided-{status}",
        requested_by=manager,
        status=status,
    )
    superadmin = make_superadmin(f"approval-decided-{status}-superadmin")

    run_action("approve_and_provision", subdomain_request, superadmin)

    makerspace.refresh_from_db()
    subdomain_request.refresh_from_db()
    assert not makerspace.frontend_domain
    assert subdomain_request.status == status
    assert subdomain_request.decided_by is None
    assert subdomain_request.decided_at is None
    assert not AuditLog.objects.filter(makerspace=makerspace).exists()


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me")
def test_approve_skips_makerspace_that_already_has_platform_subdomain():
    makerspace, _manager, subdomain_request = make_pending_request(
        "approval-already-provisioned",
        "replacement",
    )
    makerspace.frontend_domain = "x.osmm.me"
    makerspace.frontend_domain_status = Makerspace.DomainStatus.VERIFIED
    makerspace.save(
        update_fields=["frontend_domain", "frontend_domain_status", "updated_at"]
    )
    superadmin = make_superadmin("approval-already-provisioned-superadmin")

    run_action("approve_and_provision", subdomain_request, superadmin)

    makerspace.refresh_from_db()
    subdomain_request.refresh_from_db()
    assert makerspace.frontend_domain == "x.osmm.me"
    assert subdomain_request.status == SubdomainRequest.Status.PENDING
    assert subdomain_request.decided_by is None
    assert subdomain_request.decided_at is None


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me")
def test_reject_records_decision_without_provisioning_domain():
    makerspace, _manager, subdomain_request = make_pending_request(
        "approval-reject-space",
        "reject-me",
    )
    superadmin = make_superadmin("approval-reject-superadmin")

    run_action("reject_selected", subdomain_request, superadmin)

    makerspace.refresh_from_db()
    subdomain_request.refresh_from_db()
    assert not makerspace.frontend_domain
    assert subdomain_request.status == SubdomainRequest.Status.REJECTED
    assert subdomain_request.decided_by == superadmin
    assert subdomain_request.decided_at is not None
    assert AuditLog.objects.filter(
        actor=superadmin,
        action="makerspace.subdomain_request_rejected",
        makerspace=makerspace,
        target_id=str(subdomain_request.pk),
    ).exists()


@override_settings(PLATFORM_DOMAIN_SUFFIX=".osmm.me")
@pytest.mark.parametrize(
    ("action_name", "expected_status"),
    [
        ("approve_and_provision", SubdomainRequest.Status.APPROVED),
        ("reject_selected", SubdomainRequest.Status.REJECTED),
    ],
)
def test_resolution_succeeds_when_requester_has_no_email(
    action_name,
    expected_status,
):
    makerspace, manager, subdomain_request = make_pending_request(
        f"approval-no-email-{expected_status}",
        f"no-email-{expected_status}",
    )
    manager.email = ""
    manager.save(update_fields=["email"])
    superadmin = make_superadmin(f"approval-no-email-{expected_status}-superadmin")

    run_action(action_name, subdomain_request, superadmin)

    subdomain_request.refresh_from_db()
    assert subdomain_request.status == expected_status
    assert subdomain_request.decided_by == superadmin
    assert subdomain_request.decided_at is not None
    if expected_status == SubdomainRequest.Status.APPROVED:
        makerspace.refresh_from_db()
        assert makerspace.frontend_domain == f"no-email-{expected_status}.osmm.me"
