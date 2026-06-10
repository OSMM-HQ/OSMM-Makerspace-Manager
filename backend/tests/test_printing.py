import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.makerspaces.models import Makerspace, MakerspaceMembership
from apps.printing.emails import send_print_email
from apps.printing.models import PrintBucket, PrintRequest

pytestmark = pytest.mark.django_db


def make_user(username, role=User.Role.REQUESTER, **kw):
    return get_user_model().objects.create_user(
        username=username, email=f"{username}@e.com", role=role, **kw
    )


def make_space(slug):
    return Makerspace.objects.create(name=slug, slug=slug)


def make_member(
    username,
    makerspace,
    membership_role=MakerspaceMembership.Role.ADMIN,
    role=User.Role.ADMIN,
):
    user = make_user(username, role=role, access_status=User.AccessStatus.ACTIVE)
    MakerspaceMembership.objects.create(
        user=user,
        makerspace=makerspace,
        role=membership_role,
    )
    return user


def make_print_manager(username, makerspace):
    return make_member(
        username,
        makerspace,
        membership_role=MakerspaceMembership.Role.PRINT_MANAGER,
        role=User.Role.REQUESTER,
    )


def make_bucket(makerspace, name="PLA", is_active=True):
    return PrintBucket.objects.create(
        makerspace=makerspace,
        name=name,
        is_active=is_active,
    )


def make_request(bucket, requester, title="Bracket", status=PrintRequest.Status.PENDING):
    return PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title=title,
        quantity=1,
        status=status,
    )


def authenticated_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def result_ids(response):
    data = response.data
    if isinstance(data, dict) and "results" in data:
        data = data["results"]
    return {item["id"] for item in data}


def reset_outbox():
    mail.outbox = []


def request_list_url():
    return reverse("printing:request-list")


def request_detail_url(print_request):
    return reverse("printing:request-detail", kwargs={"pk": print_request.id})


def bucket_list_url():
    return reverse("printing:bucket-list")


def managed_list_url():
    return reverse("printing:managed-request-list")


def managed_detail_url(print_request):
    return reverse("printing:managed-request-detail", kwargs={"pk": print_request.id})


def action_url(print_request, action):
    return reverse(f"printing:managed-request-{action}", kwargs={"pk": print_request.id})


def printed_list_url():
    return reverse("printing:printed-list")


def test_requester_creates_lists_and_retrieves_only_own_requests():
    makerspace = make_space("printing-own")
    bucket = make_bucket(makerspace)
    requester = make_user("print-requester", access_status=User.AccessStatus.ACTIVE)
    other_requester = make_user("other-requester", access_status=User.AccessStatus.ACTIVE)
    other_request = make_request(bucket, other_requester, title="Other")
    client = authenticated_client(requester)

    response = client.post(
        request_list_url(),
        {
            "bucket": bucket.id,
            "title": "Phone stand",
            "description": "Desk accessory",
            "material": "PLA",
            "color": "black",
            "quantity": 2,
            "source_link": "https://example.com/model.stl",
        },
        format="json",
    )

    assert response.status_code == 201
    created = PrintRequest.objects.get(pk=response.data["id"])
    assert created.requester == requester
    assert created.status == PrintRequest.Status.PENDING

    response = client.get(request_list_url())
    assert response.status_code == 200
    assert result_ids(response) == {created.id}
    assert other_request.id not in result_ids(response)

    response = client.get(request_detail_url(created))
    assert response.status_code == 200
    assert response.data["id"] == created.id

    response = authenticated_client(other_requester).get(request_detail_url(created))
    assert response.status_code == 404


def test_request_create_rejects_inactive_bucket_but_allows_other_makerspace_bucket():
    own_space = make_space("printing-own-bucket")
    other_space = make_space("printing-other-bucket")
    inactive_bucket = make_bucket(own_space, name="Dormant", is_active=False)
    other_bucket = make_bucket(other_space, name="Public")
    requester = make_user("bucket-requester", access_status=User.AccessStatus.ACTIVE)
    client = authenticated_client(requester)

    response = client.post(
        request_list_url(),
        {"bucket": inactive_bucket.id, "title": "Inactive bucket", "quantity": 1},
        format="json",
    )
    assert response.status_code == 400
    assert PrintRequest.objects.count() == 0

    response = client.post(
        request_list_url(),
        {"bucket": other_bucket.id, "title": "Cross space", "quantity": 1},
        format="json",
    )
    assert response.status_code == 201
    assert PrintRequest.objects.get().bucket == other_bucket


def test_bucket_list_requires_makerspace_and_returns_active_unpaginated_buckets():
    makerspace = make_space("bucket-list")
    other_space = make_space("bucket-list-other")
    active = make_bucket(makerspace, name="A")
    inactive = make_bucket(makerspace, name="B", is_active=False)
    other = make_bucket(other_space, name="C")
    requester = make_user("bucket-list-requester", access_status=User.AccessStatus.ACTIVE)
    client = authenticated_client(requester)

    response = client.get(bucket_list_url())
    assert response.status_code == 400

    response = client.get(bucket_list_url(), {"makerspace": "abc"})
    assert response.status_code == 400

    response = client.get(bucket_list_url(), {"makerspace": makerspace.id})
    assert response.status_code == 200
    assert isinstance(response.data, list)
    assert [item["id"] for item in response.data] == [active.id]
    assert inactive.id not in result_ids(response)
    assert other.id not in result_ids(response)


@pytest.mark.parametrize(
    "access_status",
    [User.AccessStatus.RESTRICTED, User.AccessStatus.SUSPENDED],
)
def test_restricted_and_suspended_requesters_are_blocked_from_create(access_status):
    makerspace = make_space(f"blocked-{access_status}")
    bucket = make_bucket(makerspace)
    requester = make_user(
        f"blocked-{access_status}",
        access_status=access_status,
    )

    response = authenticated_client(requester).post(
        request_list_url(),
        {"bucket": bucket.id, "title": "Blocked", "quantity": 1},
        format="json",
    )

    assert response.status_code == 403
    assert PrintRequest.objects.count() == 0


def test_print_manager_accepts_starts_and_completes_with_audit_and_emails(
    settings,
    django_capture_on_commit_callbacks,
):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    reset_outbox()
    makerspace = make_space("lifecycle")
    bucket = make_bucket(makerspace)
    requester = make_user("lifecycle-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("lifecycle-manager", makerspace)
    print_request = make_request(bucket, requester)
    client = authenticated_client(manager)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = client.post(action_url(print_request, "accept"), format="json")
        assert response.status_code == 200
        assert mail.outbox == []
    assert len(callbacks) == 1
    assert len(mail.outbox) == 1
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.ACCEPTED
    assert print_request.accepted_at is not None
    assert print_request.handled_by == manager
    audit = AuditLog.objects.get(action="print.accepted")
    assert audit.makerspace == makerspace
    assert audit.target_id == str(print_request.id)

    response = client.post(action_url(print_request, "start"), format="json")
    assert response.status_code == 200
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.PRINTING
    assert AuditLog.objects.filter(action="print.started").count() == 1
    assert len(mail.outbox) == 1

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = client.post(action_url(print_request, "complete"), format="json")
        assert response.status_code == 200
        assert len(mail.outbox) == 1
    assert len(callbacks) == 1
    assert len(mail.outbox) == 2
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.COMPLETED
    assert print_request.completed_at is not None
    assert AuditLog.objects.filter(action="print.completed").count() == 1


def test_print_manager_rejects_pending_request_with_reason_audit_and_email(
    settings,
    django_capture_on_commit_callbacks,
):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    reset_outbox()
    makerspace = make_space("reject-flow")
    bucket = make_bucket(makerspace)
    requester = make_user("reject-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("reject-manager", makerspace)
    print_request = make_request(bucket, requester)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = authenticated_client(manager).post(
            action_url(print_request, "reject"),
            {"reason": "Model needs supports clarified."},
            format="json",
        )
        assert response.status_code == 200
        assert mail.outbox == []

    assert len(callbacks) == 1
    assert len(mail.outbox) == 1
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.REJECTED
    assert print_request.reason == "Model needs supports clarified."
    assert AuditLog.objects.get(action="print.rejected").target_id == str(print_request.id)


def test_print_manager_fails_printing_request_with_reason_and_no_email():
    makerspace = make_space("fail-flow")
    bucket = make_bucket(makerspace)
    requester = make_user("fail-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("fail-manager", makerspace)
    print_request = make_request(
        bucket,
        requester,
        status=PrintRequest.Status.PRINTING,
    )
    reset_outbox()

    response = authenticated_client(manager).post(
        action_url(print_request, "fail"),
        {"reason": "Nozzle jammed."},
        format="json",
    )

    assert response.status_code == 200
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.FAILED
    assert print_request.reason == "Nozzle jammed."
    assert AuditLog.objects.get(action="print.failed").target_id == str(print_request.id)
    assert mail.outbox == []


@pytest.mark.parametrize(
    ("initial_status", "action"),
    [
        (PrintRequest.Status.PENDING, "complete"),
        (PrintRequest.Status.ACCEPTED, "accept"),
    ],
)
def test_invalid_transition_returns_409_without_audit_or_email(
    settings,
    django_capture_on_commit_callbacks,
    initial_status,
    action,
):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    reset_outbox()
    makerspace = make_space(f"invalid-{initial_status}-{action}")
    bucket = make_bucket(makerspace)
    requester = make_user(
        f"invalid-requester-{initial_status}-{action}",
        access_status=User.AccessStatus.ACTIVE,
    )
    manager = make_print_manager(f"invalid-manager-{initial_status}-{action}", makerspace)
    print_request = make_request(bucket, requester, status=initial_status)
    audit_count = AuditLog.objects.count()

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = authenticated_client(manager).post(
            action_url(print_request, action),
            format="json",
        )

    assert response.status_code == 409
    assert len(callbacks) == 0
    assert AuditLog.objects.count() == audit_count
    assert mail.outbox == []
    print_request.refresh_from_db()
    assert print_request.status == initial_status


def test_manage_rbac_requester_manager_scope_cross_tenant_and_superadmin():
    own_space = make_space("manage-own")
    other_space = make_space("manage-other")
    own_bucket = make_bucket(own_space)
    other_bucket = make_bucket(other_space)
    requester = make_user("manage-requester", access_status=User.AccessStatus.ACTIVE)
    plain_requester = make_user("plain-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("scoped-manager", own_space)
    superadmin = make_user(
        "printing-superadmin",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )
    own_request = make_request(own_bucket, requester, title="Own")
    other_request = make_request(other_bucket, requester, title="Other")

    response = authenticated_client(plain_requester).get(managed_list_url())
    assert response.status_code == 200
    assert result_ids(response) == set()

    response = authenticated_client(plain_requester).post(
        action_url(own_request, "accept"),
        format="json",
    )
    assert response.status_code == 403

    manager_client = authenticated_client(manager)
    response = manager_client.get(managed_list_url())
    assert response.status_code == 200
    assert result_ids(response) == {own_request.id}

    response = manager_client.get(managed_list_url(), {"makerspace": own_space.id})
    assert response.status_code == 200
    assert result_ids(response) == {own_request.id}

    response = manager_client.post(action_url(other_request, "accept"), format="json")
    assert response.status_code == 404

    response = manager_client.get(managed_detail_url(other_request))
    assert response.status_code == 404

    response = authenticated_client(superadmin).get(managed_list_url())
    assert response.status_code == 200
    assert result_ids(response) == {own_request.id, other_request.id}


def test_guest_admin_without_manage_printing_gets_empty_list_or_403_with_makerspace():
    makerspace = make_space("guest-admin-printing")
    bucket = make_bucket(makerspace)
    requester = make_user("guest-admin-requester", access_status=User.AccessStatus.ACTIVE)
    guest_admin = make_member(
        "guest-admin-printing-user",
        makerspace,
        membership_role=MakerspaceMembership.Role.GUEST_ADMIN,
        role=User.Role.GUEST_ADMIN,
    )
    print_request = make_request(bucket, requester)
    client = authenticated_client(guest_admin)

    response = client.get(managed_list_url())
    assert response.status_code == 200
    assert result_ids(response) == set()

    response = client.get(managed_list_url(), {"makerspace": makerspace.id})
    assert response.status_code == 403
    assert PrintRequest.objects.filter(pk=print_request.pk).exists()


def test_printed_list_returns_only_completed_requests_in_action_scope():
    own_space = make_space("printed-own")
    other_space = make_space("printed-other")
    own_bucket = make_bucket(own_space)
    other_bucket = make_bucket(other_space)
    requester = make_user("printed-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("printed-manager", own_space)
    own_completed = make_request(
        own_bucket,
        requester,
        title="Done",
        status=PrintRequest.Status.COMPLETED,
    )
    own_pending = make_request(own_bucket, requester, title="Todo")
    other_completed = make_request(
        other_bucket,
        requester,
        title="Other done",
        status=PrintRequest.Status.COMPLETED,
    )

    response = authenticated_client(manager).get(printed_list_url())

    assert response.status_code == 200
    assert result_ids(response) == {own_completed.id}
    assert own_pending.id not in result_ids(response)
    assert other_completed.id not in result_ids(response)


@pytest.mark.parametrize(
    ("event", "status", "reason"),
    [
        ("accepted", PrintRequest.Status.ACCEPTED, ""),
        ("rejected", PrintRequest.Status.REJECTED, "Too fragile."),
        ("completed", PrintRequest.Status.COMPLETED, ""),
    ],
)
def test_print_email_templates_render_subject_and_branded_html(
    settings,
    event,
    status,
    reason,
):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    reset_outbox()
    makerspace = make_space(f"template-{event}")
    bucket = make_bucket(makerspace)
    requester = make_user(
        f"template-requester-{event}",
        access_status=User.AccessStatus.ACTIVE,
    )
    print_request = make_request(bucket, requester, status=status)
    if reason:
        print_request.reason = reason
        print_request.save(update_fields=["reason", "updated_at"])

    send_print_email(event, print_request)

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.subject
    assert len(message.alternatives) == 1
    html, mimetype = message.alternatives[0]
    assert mimetype == "text/html"
    assert "TinkerSpace" in html
    assert "background:#111111;color:#FBB905" in html


def test_printbucket_admin_scope_is_action_aware_not_raw_membership():
    """A global-admin who is only a guest_admin MEMBER of a space must not see
    that space's buckets in the printing admin (Stage 4 P2 fix)."""
    from django.contrib.admin.sites import AdminSite
    from django.test import RequestFactory

    from apps.printing.admin import PrintBucketAdmin

    managed = make_space("admin-managed")
    other = make_space("admin-guest-only")
    # global ADMIN, but only an ADMIN member of `managed` and guest_admin of `other`.
    user = make_member(
        "dual-role-admin",
        managed,
        membership_role=MakerspaceMembership.Role.ADMIN,
        role=User.Role.ADMIN,
    )
    MakerspaceMembership.objects.create(
        user=user, makerspace=other, role=MakerspaceMembership.Role.GUEST_ADMIN
    )
    in_scope = make_bucket(managed, name="In scope")
    out_of_scope = make_bucket(other, name="Out of scope")

    request = RequestFactory().get("/admin/printing/printbucket/")
    request.user = user
    qs = PrintBucketAdmin(PrintBucket, AdminSite()).get_queryset(request)

    ids = set(qs.values_list("id", flat=True))
    assert in_scope.id in ids
    assert out_of_scope.id not in ids
