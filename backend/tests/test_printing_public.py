from uuid import uuid4

import pytest
from django.core import mail
from django.urls import reverse
from rest_framework.test import APIClient

from apps.printing.models import FilamentSpool, PrintBucket, PrintRequest, PrintRequestFile
from tests.test_printing import make_bucket, make_space, make_user

pytestmark = pytest.mark.django_db


def enable_printing(makerspace):
    makerspace.enabled_modules = ["printing"]
    makerspace.save(update_fields=["enabled_modules"])


def public_client():
    return APIClient()


def submit_url(makerspace):
    return reverse(
        "printing:public-request-submit",
        kwargs={"makerspace_slug": makerspace.slug},
    )


def presign_url(makerspace):
    return reverse(
        "printing:public-upload-presign",
        kwargs={"makerspace_slug": makerspace.slug},
    )


def status_url(public_token):
    return reverse(
        "printing:public-request-status",
        kwargs={"public_token": str(public_token)},
    )


def status_by_email_url(makerspace):
    return reverse(
        "printing:public-request-status-by-email",
        kwargs={"makerspace_slug": makerspace.slug},
    )


def mock_upload(monkeypatch):
    monkeypatch.setattr(
        "apps.printing.public_views.presigned_print_upload",
        lambda object_key, content_type: {
            "url": "http://minio/printing",
            "fields": {"key": object_key, "Content-Type": content_type},
        },
    )


def buckets_url(makerspace):
    return reverse(
        "printing:public-buckets",
        kwargs={"makerspace_slug": makerspace.slug},
    )


def spools_url(makerspace):
    return reverse(
        "printing:public-spools",
        kwargs={"makerspace_slug": makerspace.slug},
    )


def checkin_verify_url(makerspace):
    return reverse(
        "printing:public-checkin-verify",
        kwargs={"makerspace_slug": makerspace.slug},
    )


def test_checkin_verify_omits_external_id():
    makerspace = make_space("public-print-verify")
    enable_printing(makerspace)

    response = public_client().post(
        checkin_verify_url(makerspace),
        {"identifier": "u@e.com"},
        format="json",
    )

    assert response.status_code == 200
    assert set(response.data.keys()) == {"username"}


def test_presign_blocked_for_inactive_requester(monkeypatch):
    from apps.accounts.models import User

    makerspace = make_space("public-print-presign-blocked")
    enable_printing(makerspace)
    User.objects.create(
        username="blocked-checkin",
        external_checkin_user_id="blocked@e.com",
        access_status=User.AccessStatus.SUSPENDED,
    )
    mock_upload(monkeypatch)

    response = public_client().post(
        presign_url(makerspace),
        {
            "identifier": "blocked@e.com",
            "kind": "stl",
            "filename": "p.stl",
            "content_type": "application/octet-stream",
        },
        format="json",
    )

    assert response.status_code == 403
    assert not PrintRequestFile.objects.exists()


def test_public_buckets_lists_active_only():
    makerspace = make_space("public-print-buckets")
    enable_printing(makerspace)
    active = make_bucket(makerspace, name="PLA")
    make_bucket(makerspace, name="Retired", is_active=False)

    response = public_client().get(buckets_url(makerspace))

    assert response.status_code == 200
    ids = [bucket["id"] for bucket in response.data]
    assert ids == [active.id]


def test_public_submit_creates_pending_request():
    makerspace = make_space("public-print-submit")
    enable_printing(makerspace)
    bucket = make_bucket(makerspace)

    response = public_client().post(
        submit_url(makerspace),
        {"identifier": "u@e.com", "bucket_id": bucket.id, "title": "Bracket"},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["public_token"]
    assert response.data["status"] == PrintRequest.Status.PENDING
    created = PrintRequest.objects.get()
    assert created.requester.external_checkin_user_id == "u@e.com"


def test_public_submit_without_bucket_uses_public_requests_bucket():
    makerspace = make_space("public-print-default-bucket")
    enable_printing(makerspace)

    response = public_client().post(
        submit_url(makerspace),
        {"identifier": "u@e.com", "title": "Bracket"},
        format="json",
    )

    assert response.status_code == 201
    bucket = PrintBucket.objects.get(makerspace=makerspace, name="Public Requests")
    created = PrintRequest.objects.get()
    assert created.bucket == bucket


def test_public_submit_with_requested_spool_preserves_operational_spool():
    makerspace = make_space("public-print-requested-spool")
    enable_printing(makerspace)
    bucket = make_bucket(makerspace)
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        material="PETG",
        color="orange",
        brand="Internal Brand",
        lot_code="LOT-1",
        initial_weight_grams=1000,
        remaining_weight_grams=750,
    )

    response = public_client().post(
        submit_url(makerspace),
        {
            "identifier": "u@e.com",
            "bucket_id": bucket.id,
            "title": "Spool request",
            "filament_spool_id": spool.id,
        },
        format="json",
    )

    assert response.status_code == 201
    created = PrintRequest.objects.get()
    assert created.requested_filament_spool == spool
    assert created.filament_spool is None
    assert created.material == "PETG"
    assert created.color == "orange"


@pytest.mark.parametrize("spool_case", ["foreign", "inactive"])
def test_public_submit_rejects_foreign_or_inactive_requested_spool(spool_case):
    makerspace = make_space(f"public-print-bad-spool-{spool_case}")
    other_space = make_space(f"public-print-bad-spool-{spool_case}-other")
    enable_printing(makerspace)
    enable_printing(other_space)
    bucket = make_bucket(makerspace)
    spool_space = other_space if spool_case == "foreign" else makerspace
    spool = FilamentSpool.objects.create(
        makerspace=spool_space,
        material="PLA",
        color="black",
        initial_weight_grams=1000,
        remaining_weight_grams=500,
        is_active=spool_case != "inactive",
    )

    response = public_client().post(
        submit_url(makerspace),
        {
            "identifier": "u@e.com",
            "bucket_id": bucket.id,
            "title": "Bad spool request",
            "filament_spool_id": spool.id,
        },
        format="json",
    )

    assert response.status_code == 400
    assert not PrintRequest.objects.exists()


def test_public_submit_persists_requester_name():
    makerspace = make_space("public-print-requester-name")
    enable_printing(makerspace)
    bucket = make_bucket(makerspace)

    response = public_client().post(
        submit_url(makerspace),
        {
            "identifier": "u@e.com",
            "bucket_id": bucket.id,
            "requester_name": "Uma Example",
            "title": "Named request",
        },
        format="json",
    )

    assert response.status_code == 201
    assert PrintRequest.objects.get().requester_name == "Uma Example"


def test_public_spools_lists_active_same_space_safe_fields_only():
    makerspace = make_space("public-print-spools")
    other_space = make_space("public-print-spools-other")
    enable_printing(makerspace)
    enable_printing(other_space)
    active = FilamentSpool.objects.create(
        makerspace=makerspace,
        material="PLA",
        color="white",
        brand="Hidden Brand",
        lot_code="HIDDEN-LOT",
        initial_weight_grams=1000,
        remaining_weight_grams=640,
    )
    FilamentSpool.objects.create(
        makerspace=makerspace,
        material="PETG",
        color="blue",
        initial_weight_grams=1000,
        remaining_weight_grams=100,
        is_active=False,
    )
    FilamentSpool.objects.create(
        makerspace=other_space,
        material="ABS",
        color="red",
        initial_weight_grams=1000,
        remaining_weight_grams=200,
    )

    response = public_client().get(spools_url(makerspace))

    assert response.status_code == 200
    assert response.data == [
        {
            "id": active.id,
            "material": "PLA",
            "color": "white",
            "remaining_weight_grams": "640.00",
        }
    ]
    assert set(response.data[0].keys()) == {
        "id",
        "material",
        "color",
        "remaining_weight_grams",
    }


def test_honeypot_returns_decoy_and_creates_nothing():
    makerspace = make_space("public-print-honeypot")
    enable_printing(makerspace)
    bucket = make_bucket(makerspace)
    before = PrintRequest.objects.count()

    response = public_client().post(
        submit_url(makerspace),
        {
            "identifier": "u@e.com",
            "bucket_id": bucket.id,
            "title": "X",
            "website": "bot",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["status"] == PrintRequest.Status.PENDING
    assert PrintRequest.objects.count() == before


def test_module_off_blocks_submit():
    makerspace = make_space("public-print-off")
    makerspace.enabled_modules = ["public_inventory"]
    makerspace.save(update_fields=["enabled_modules"])
    bucket = make_bucket(makerspace)

    response = public_client().post(
        submit_url(makerspace),
        {"identifier": "u@e.com", "bucket_id": bucket.id, "title": "Bracket"},
        format="json",
    )

    assert response.status_code == 400


def test_status_lookup_by_token_hides_pii():
    makerspace = make_space("public-print-status")
    enable_printing(makerspace)
    bucket = make_bucket(makerspace)
    client = public_client()
    client.post(
        submit_url(makerspace),
        {"identifier": "u@e.com", "bucket_id": bucket.id, "title": "Bracket"},
        format="json",
    )
    print_request = PrintRequest.objects.get()

    response = client.get(status_url(print_request.public_token))

    assert response.status_code == 200
    assert set(response.data.keys()) == {
        "public_token",
        "status",
        "title",
        "created_at",
        "accepted_at",
        "started_at",
        "completed_at",
        "estimated_minutes",
        "queue_position",
        "queue_approved_ahead",
        "queue_awaiting_review_ahead",
    }


def test_status_lookup_by_email_lists_recent_same_space_requests():
    makerspace = make_space("public-print-status-email")
    other_space = make_space("public-print-status-email-other")
    enable_printing(makerspace)
    enable_printing(other_space)
    bucket = make_bucket(makerspace)
    other_bucket = make_bucket(other_space)
    requester = make_user("public-status-email-requester")
    old_request = PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Old bracket",
        contact_email="Buyer@Example.com",
    )
    new_request = PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="New bracket",
        contact_email="buyer@example.com",
    )
    PrintRequest.objects.create(
        bucket=other_bucket,
        requester=requester,
        title="Other space",
        contact_email="buyer@example.com",
    )

    response = public_client().post(
        status_by_email_url(makerspace),
        {"email": "BUYER@example.com"},
        format="json",
    )

    assert response.status_code == 200
    assert [item["public_token"] for item in response.data["results"]] == [
        str(new_request.public_token),
        str(old_request.public_token),
    ]


def test_status_lookup_by_email_returns_empty_results():
    makerspace = make_space("public-print-status-email-empty")
    enable_printing(makerspace)

    response = public_client().post(
        status_by_email_url(makerspace),
        {"email": "missing@example.com"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data == {"results": []}


def test_status_lookup_by_email_rejects_invalid_email():
    makerspace = make_space("public-print-status-email-invalid")
    enable_printing(makerspace)

    response = public_client().post(
        status_by_email_url(makerspace),
        {"email": "not-an-email"},
        format="json",
    )

    assert response.status_code == 400


def test_status_unknown_token_404():
    response = public_client().get(status_url(uuid4()))

    assert response.status_code == 404


def test_presign_rejects_bad_mime_and_accepts_good(monkeypatch):
    makerspace = make_space("public-print-presign")
    enable_printing(makerspace)
    mock_upload(monkeypatch)
    client = public_client()

    response = client.post(
        presign_url(makerspace),
        {
            "identifier": "u@e.com",
            "kind": "screenshot",
            "filename": "x.png",
            "content_type": "application/pdf",
        },
        format="json",
    )
    assert response.status_code == 400

    response = client.post(
        presign_url(makerspace),
        {
            "identifier": "u@e.com",
            "kind": "stl",
            "filename": "p.stl",
            "content_type": "application/octet-stream",
        },
        format="json",
    )
    assert response.status_code == 201
    assert "file_id" in response.data
    assert "upload" in response.data
    assert PrintRequestFile.objects.get(pk=response.data["file_id"]).original_filename == "p.stl"


def test_submit_rejects_foreign_file_id(monkeypatch):
    makerspace = make_space("public-print-foreign-file")
    enable_printing(makerspace)
    bucket = make_bucket(makerspace)
    upload = PrintRequestFile.objects.create(
        makerspace=makerspace,
        kind=PrintRequestFile.Kind.STL,
        object_key=f"print/{makerspace.id}/stl/foreign",
        content_type="application/octet-stream",
        owner_checkin_user_id="other",
    )
    monkeypatch.setattr("apps.printing.public_workflow.print_object_size", lambda key: 10)
    before = PrintRequest.objects.count()

    response = public_client().post(
        submit_url(makerspace),
        {
            "identifier": "u@e.com",
            "bucket_id": bucket.id,
            "title": "Bracket",
            "file_ids": [upload.id],
        },
        format="json",
    )

    assert response.status_code == 400
    assert PrintRequest.objects.count() == before


def test_submit_attaches_owned_file(monkeypatch):
    makerspace = make_space("public-print-owned-file")
    enable_printing(makerspace)
    bucket = make_bucket(makerspace)
    mock_upload(monkeypatch)
    client = public_client()
    response = client.post(
        presign_url(makerspace),
        {
            "identifier": "u@e.com",
            "kind": "stl",
            "filename": "p.stl",
            "content_type": "application/octet-stream",
        },
        format="json",
    )
    file_id = response.data["file_id"]
    monkeypatch.setattr("apps.printing.public_workflow.print_object_size", lambda key: 123)

    response = client.post(
        submit_url(makerspace),
        {
            "identifier": "u@e.com",
            "bucket_id": bucket.id,
            "title": "Bracket",
            "file_ids": [file_id],
        },
        format="json",
    )

    assert response.status_code == 201
    upload = PrintRequestFile.objects.get(pk=file_id)
    assert upload.attached_at is not None
    assert upload.print_request is not None
    assert upload.size_bytes == 123


def test_public_submit_rejects_zero_byte_upload(monkeypatch):
    makerspace = make_space("public-print-zero-byte")
    enable_printing(makerspace)
    bucket = make_bucket(makerspace)
    upload = PrintRequestFile.objects.create(
        makerspace=makerspace,
        kind=PrintRequestFile.Kind.STL,
        object_key=f"print/{makerspace.id}/stl/zero",
        content_type="application/octet-stream",
        owner_checkin_user_id="u@e.com",
    )
    monkeypatch.setattr("apps.printing.public_workflow.print_object_size", lambda key: 0)

    response = public_client().post(
        submit_url(makerspace),
        {
            "identifier": "u@e.com",
            "bucket_id": bucket.id,
            "title": "Bracket",
            "file_ids": [upload.id],
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["file_ids"] == "An uploaded file exceeds the size limit."
    upload.refresh_from_db()
    assert upload.print_request is None
    assert upload.attached_at is None


def test_public_submit_emails_contact_email(settings, django_capture_on_commit_callbacks):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox.clear()
    makerspace = make_space("public-print-email")
    enable_printing(makerspace)
    bucket = make_bucket(makerspace)

    with django_capture_on_commit_callbacks(execute=True):
        response = public_client().post(
            submit_url(makerspace),
            {
                "identifier": "u@e.com",
                "bucket_id": bucket.id,
                "title": "Bracket",
                "contact_email": "buyer@example.com",
            },
            format="json",
        )

    assert response.status_code == 201
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["buyer@example.com"]
