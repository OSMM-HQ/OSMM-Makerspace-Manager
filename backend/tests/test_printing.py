from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.makerspaces.models import Makerspace, MakerspaceMembership
from apps.printing.emails import send_print_email
from apps.printing.models import (
    FilamentSpool,
    PrintBucket,
    PrintPrinter,
    PrintRequest,
    PrintRequestFile,
)
from apps.printing.serializers import PrintRequestSerializer
from apps.printing import workflow

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
    membership_role=MakerspaceMembership.Role.SPACE_MANAGER,
    role=User.Role.SPACE_MANAGER,
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


def makerspace_report_url(makerspace):
    return reverse(
        "printing:makerspace-report",
        kwargs={"makerspace_id": makerspace.id},
    )


def printer_list_url():
    return reverse("printing:managed-printer-list")


def printer_detail_url(printer):
    return reverse("printing:managed-printer-detail", kwargs={"pk": printer.id})


def spool_list_url():
    return reverse("printing:managed-spool-list")


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


def test_requester_uploads_model_settings_and_bambu_screenshots(tmp_path):
    makerspace = make_space("printing-files")
    bucket = make_bucket(makerspace)
    requester = make_user("print-file-requester", access_status=User.AccessStatus.ACTIVE)
    client = authenticated_client(requester)

    with override_settings(
        MEDIA_ROOT=tmp_path,
        STORAGES={
            "default": {
                "BACKEND": "django.core.files.storage.FileSystemStorage",
            },
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
            },
        },
    ):
        response = client.post(
            request_list_url(),
            {
                "bucket": bucket.id,
                "title": "Bracket with files",
                "quantity": 1,
                "model_file": SimpleUploadedFile(
                    "bracket.stl",
                    b"solid bracket\nendsolid bracket\n",
                    content_type="model/stl",
                ),
                "preferred_settings": "0.2mm layer height, 15% gyroid infill",
                "estimate_screenshot": SimpleUploadedFile(
                    "estimate.png",
                    b"estimate image",
                    content_type="image/png",
                ),
                "preview_screenshot": SimpleUploadedFile(
                    "preview.png",
                    b"preview image",
                    content_type="image/png",
                ),
            },
        )

    assert response.status_code == 201
    created = PrintRequest.objects.get(pk=response.data["id"])
    assert created.model_file.name.endswith(".stl")
    assert created.preferred_settings == "0.2mm layer height, 15% gyroid infill"
    assert created.estimate_screenshot.name.endswith(".png")
    assert created.preview_screenshot.name.endswith(".png")
    assert response.data["model_file"]
    assert response.data["estimate_screenshot"]
    assert response.data["preview_screenshot"]


def test_requester_upload_rejects_non_model_file():
    makerspace = make_space("printing-bad-file")
    bucket = make_bucket(makerspace)
    requester = make_user("bad-file-requester", access_status=User.AccessStatus.ACTIVE)

    response = authenticated_client(requester).post(
        request_list_url(),
        {
            "bucket": bucket.id,
            "title": "Bad file",
            "quantity": 1,
            "model_file": SimpleUploadedFile("notes.txt", b"not a model"),
        },
    )

    assert response.status_code == 400
    assert PrintRequest.objects.count() == 0


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
    # 4 = 2 sends (requester + staff) x async double-on_commit (queue hook -> dispatch enqueue hook).
    assert len(callbacks) == 4
    assert len(mail.outbox) == 2
    assert ["lifecycle-requester@e.com"] in [message.to for message in mail.outbox]
    assert ["lifecycle-manager@e.com"] in [message.to for message in mail.outbox]
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.ACCEPTED
    assert print_request.accepted_at is not None
    assert print_request.handled_by == manager
    audit = AuditLog.objects.get(action="print.accepted")
    assert audit.makerspace == makerspace
    assert audit.target_id == str(print_request.id)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = client.post(action_url(print_request, "start"), format="json")
        assert response.status_code == 200
    # 4 = 2 sends (requester + staff) x async double-on_commit (queue hook -> dispatch enqueue hook).
    assert len(callbacks) == 4
    assert len(mail.outbox) == 4
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.PRINTING
    assert AuditLog.objects.filter(action="print.started").count() == 1

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = client.post(action_url(print_request, "complete"), format="json")
        assert response.status_code == 200
        assert len(mail.outbox) == 4
    # 4 = 2 sends (requester + staff) x async double-on_commit (queue hook -> dispatch enqueue hook).
    assert len(callbacks) == 4
    assert len(mail.outbox) == 6
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.COMPLETED
    assert print_request.completed_at is not None
    assert AuditLog.objects.filter(action="print.completed").count() == 1


def test_complete_decrements_spool_remaining_and_report_filament_used():
    makerspace = make_space("spool-deduct")
    bucket = make_bucket(makerspace)
    requester = make_user("spool-deduct-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("spool-deduct-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        color="black",
        initial_weight_grams=1000,
        remaining_weight_grams=1000,
    )
    print_request = make_request(bucket, requester)

    workflow.accept(print_request, manager)
    workflow.start(
        print_request,
        manager,
        printer_id=printer.id,
        filament_spool_id=spool.id,
        estimated_minutes=60,
        estimated_filament_grams=Decimal("100.00"),
    )
    workflow.complete(print_request, manager)

    spool.refresh_from_db()
    assert spool.remaining_weight_grams == Decimal("900.00")
    print_request.refresh_from_db()
    assert print_request.filament_grams_used == Decimal("100.00")
    assert print_request.filament_grams_reserved == Decimal("0.00")
    assert AuditLog.objects.filter(action="print.spool_reserved").count() == 1
    assert AuditLog.objects.filter(action="print.spool_reconciled").count() == 1

    response = authenticated_client(manager).get(makerspace_report_url(makerspace))

    assert response.status_code == 200
    assert response.data["filament_used"] == [
        {
            "spool_id": spool.id,
            "material": "PLA",
            "color": "black",
            "grams_used": 100.0,
            "remaining_grams": 900.0,
        }
    ]


def test_fail_with_percent_charges_partial_filament():
    makerspace = make_space("spool-fail-partial")
    bucket = make_bucket(makerspace)
    requester = make_user("spool-fail-partial-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("spool-fail-partial-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        color="black",
        initial_weight_grams=1000,
        remaining_weight_grams=1000,
    )
    print_request = make_request(bucket, requester)

    workflow.accept(print_request, manager)
    workflow.start(
        print_request,
        manager,
        printer_id=printer.id,
        filament_spool_id=spool.id,
        estimated_minutes=60,
        estimated_filament_grams=Decimal("100.00"),
    )
    workflow.fail(print_request, manager, "warped", percent_complete=40)

    spool.refresh_from_db()
    assert spool.remaining_weight_grams == Decimal("960.00")
    print_request.refresh_from_db()
    assert print_request.filament_grams_used == Decimal("40.00")
    assert print_request.filament_grams_reserved == Decimal("0.00")
    assert AuditLog.objects.filter(action="print.spool_reconciled").exists()


def test_fail_with_zero_percent_does_not_charge():
    makerspace = make_space("spool-fail-zero")
    bucket = make_bucket(makerspace)
    requester = make_user("spool-fail-zero-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("spool-fail-zero-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        color="black",
        initial_weight_grams=1000,
        remaining_weight_grams=1000,
    )
    print_request = make_request(bucket, requester)

    workflow.accept(print_request, manager)
    workflow.start(
        print_request,
        manager,
        printer_id=printer.id,
        filament_spool_id=spool.id,
        estimated_minutes=60,
        estimated_filament_grams=Decimal("100.00"),
    )
    workflow.fail(print_request, manager, "warped", percent_complete=0)

    spool.refresh_from_db()
    assert spool.remaining_weight_grams == Decimal("1000.00")
    print_request.refresh_from_db()
    assert print_request.filament_grams_used == Decimal("0.00")
    assert print_request.filament_grams_reserved == Decimal("0.00")


def test_complete_rejects_unreserved_filament_overdraw():
    makerspace = make_space("spool-deduct-clamp")
    bucket = make_bucket(makerspace)
    requester = make_user("spool-clamp-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("spool-clamp-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PETG",
        initial_weight_grams=100,
        remaining_weight_grams=10,
    )
    print_request = make_request(bucket, requester)

    workflow.accept(print_request, manager)
    workflow.start(
        print_request,
        manager,
        printer_id=printer.id,
        filament_spool_id=spool.id,
        estimated_minutes=20,
        estimated_filament_grams=Decimal("5.00"),
    )
    PrintRequest.objects.filter(pk=print_request.pk).update(
        estimated_filament_grams=Decimal("100000.00")
    )
    with pytest.raises(workflow.InvalidTransition):
        workflow.complete(print_request, manager)

    spool.refresh_from_db()
    assert spool.remaining_weight_grams == Decimal("5.00")


def test_fail_does_not_decrement_spool_remaining():
    makerspace = make_space("spool-fail-no-deduct")
    bucket = make_bucket(makerspace)
    requester = make_user("spool-fail-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("spool-fail-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        initial_weight_grams=1000,
        remaining_weight_grams=1000,
    )
    print_request = make_request(bucket, requester)

    workflow.accept(print_request, manager)
    workflow.start(
        print_request,
        manager,
        printer_id=printer.id,
        filament_spool_id=spool.id,
        estimated_minutes=60,
        estimated_filament_grams=Decimal("100.00"),
    )
    workflow.fail(print_request, manager, "Nozzle jammed.")

    spool.refresh_from_db()
    assert spool.remaining_weight_grams == Decimal("1000.00")
    print_request.refresh_from_db()
    assert print_request.filament_grams_reserved == Decimal("0.00")
    assert AuditLog.objects.filter(action="print.spool_reconciled").exists()


def test_reprint_clones_failed_request():
    makerspace = make_space("reprint-clone")
    bucket = make_bucket(makerspace)
    requester = make_user("reprint-clone-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("reprint-clone-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        color="black",
        initial_weight_grams=1000,
        remaining_weight_grams=1000,
    )
    failed = make_request(bucket, requester, title="Failed bracket")
    failed.material = "PLA"
    failed.color = "black"
    failed.requested_filament_spool = spool
    failed.save(
        update_fields=[
            "material",
            "color",
            "requested_filament_spool",
            "updated_at",
        ]
    )

    workflow.accept(failed, manager)
    workflow.start(
        failed,
        manager,
        printer_id=printer.id,
        filament_spool_id=spool.id,
        estimated_minutes=60,
        estimated_filament_grams=Decimal("100.00"),
    )
    workflow.fail(failed, manager, "warped", percent_complete=40)
    failed.refresh_from_db()
    new_request = workflow.reprint(failed, manager)

    assert new_request.id != failed.id
    assert new_request.status == PrintRequest.Status.ACCEPTED
    assert new_request.reprint_of_id == failed.id
    assert new_request.printer_id is None
    assert new_request.filament_spool_id is None
    assert new_request.filament_grams_used == Decimal("0")
    assert new_request.estimated_filament_grams == failed.estimated_filament_grams
    assert new_request.requested_filament_spool_id == failed.requested_filament_spool_id
    assert new_request.accepted_at is not None
    assert new_request.started_at is None
    assert new_request.completed_at is None
    failed.refresh_from_db()
    assert failed.status == PrintRequest.Status.FAILED
    assert AuditLog.objects.filter(action="print.reprinted").exists()


def test_reprint_rejects_non_failed():
    makerspace = make_space("reprint-non-failed")
    bucket = make_bucket(makerspace)
    requester = make_user("reprint-non-failed-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("reprint-non-failed-manager", makerspace)
    print_request = make_request(
        bucket,
        requester,
        status=PrintRequest.Status.ACCEPTED,
    )

    with pytest.raises(workflow.InvalidTransition):
        workflow.reprint(print_request, manager)


def test_reprint_borrows_original_files():
    makerspace = make_space("reprint-files")
    bucket = make_bucket(makerspace)
    requester = make_user("reprint-files-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("reprint-files-manager", makerspace)
    print_request = make_request(bucket, requester)
    print_file = PrintRequestFile.objects.create(
        print_request=print_request,
        makerspace=makerspace,
        kind=PrintRequestFile.Kind.STL,
        object_key="printing/reprint-files/m.stl",
        content_type="model/stl",
        original_filename="m.stl",
        size_bytes=1234,
        owner_checkin_user_id="x",
    )
    PrintRequest.objects.filter(pk=print_request.pk).update(
        status=PrintRequest.Status.FAILED,
    )
    print_request.refresh_from_db()

    new_request = workflow.reprint(print_request, manager)
    files = PrintRequestSerializer(new_request).data["files"]

    assert len(files) == 1
    assert files[0]["id"] == print_file.id


def test_reprint_of_a_reprint_still_resolves_original_files():
    # A reprint can itself fail and be reprinted again. Every reprint must anchor to
    # the file-owning original root so the model files stay reachable across retries.
    makerspace = make_space("reprint-chain")
    bucket = make_bucket(makerspace)
    requester = make_user("reprint-chain-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("reprint-chain-manager", makerspace)
    original = make_request(bucket, requester)
    original_file = PrintRequestFile.objects.create(
        print_request=original,
        makerspace=makerspace,
        kind=PrintRequestFile.Kind.STL,
        object_key="printing/reprint-chain/m.stl",
        content_type="model/stl",
        original_filename="m.stl",
        size_bytes=1234,
        owner_checkin_user_id="x",
    )
    PrintRequest.objects.filter(pk=original.pk).update(status=PrintRequest.Status.FAILED)
    original.refresh_from_db()

    first_reprint = workflow.reprint(original, manager)
    PrintRequest.objects.filter(pk=first_reprint.pk).update(status=PrintRequest.Status.FAILED)
    first_reprint.refresh_from_db()

    second_reprint = workflow.reprint(first_reprint, manager)

    # Both reprints anchor to the original root, not the immediate failed parent.
    assert first_reprint.reprint_of_id == original.id
    assert second_reprint.reprint_of_id == original.id
    files = PrintRequestSerializer(second_reprint).data["files"]
    assert len(files) == 1
    assert files[0]["id"] == original_file.id


def test_reprint_endpoint_returns_201_and_409():
    makerspace = make_space("reprint-endpoint")
    bucket = make_bucket(makerspace)
    requester = make_user("reprint-endpoint-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("reprint-endpoint-manager", makerspace)
    failed = make_request(bucket, requester, status=PrintRequest.Status.FAILED)
    accepted = make_request(
        bucket,
        requester,
        title="Accepted",
        status=PrintRequest.Status.ACCEPTED,
    )
    client = authenticated_client(manager)

    response = client.post(
        reverse("printing:managed-request-reprint", kwargs={"pk": failed.id}),
        format="json",
    )

    assert response.status_code == 201
    assert response.data["reprint_of"] == failed.id

    response = client.post(
        reverse("printing:managed-request-reprint", kwargs={"pk": accepted.id}),
        format="json",
    )

    assert response.status_code == 409


def test_printer_outcomes_in_report():
    makerspace = make_space("printer-outcomes")
    bucket = make_bucket(makerspace)
    requester = make_user("printer-outcomes-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("printer-outcomes-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        color="black",
        initial_weight_grams=1000,
        remaining_weight_grams=1000,
    )
    completed = make_request(bucket, requester, title="Completed")
    failed = make_request(bucket, requester, title="Failed")

    workflow.accept(completed, manager)
    workflow.start(
        completed,
        manager,
        printer_id=printer.id,
        filament_spool_id=spool.id,
        estimated_minutes=60,
        estimated_filament_grams=Decimal("100.00"),
    )
    workflow.complete(completed, manager)

    workflow.accept(failed, manager)
    workflow.start(
        failed,
        manager,
        printer_id=printer.id,
        filament_spool_id=spool.id,
        estimated_minutes=30,
        estimated_filament_grams=Decimal("100.00"),
    )
    workflow.fail(failed, manager, "warped", percent_complete=40)

    response = authenticated_client(manager).get(makerspace_report_url(makerspace))

    assert response.status_code == 200
    assert response.data["printer_outcomes"] == [
        {
            "printer_id": printer.id,
            "printer_name": "Prusa MK4",
            "completed": 1,
            "failed": 1,
            "grams_used": 140.0,
            "manual_logs": 0,
        }
    ]


def test_print_manager_creates_printer_and_spool_in_action_scope():
    makerspace = make_space("printer-scope")
    other_space = make_space("printer-other")
    manager = make_print_manager("printer-manager", makerspace)
    guest = make_member(
        "printer-guest",
        makerspace,
        membership_role=MakerspaceMembership.Role.GUEST_ADMIN,
        role=User.Role.GUEST_ADMIN,
    )
    client = authenticated_client(manager)

    response = client.post(
        printer_list_url(),
        {
            "makerspace": makerspace.id,
            "name": "Bambu A1",
            "model": "A1 Combo",
            "status": "active",
        },
        format="json",
    )

    assert response.status_code == 201
    printer = PrintPrinter.objects.get(pk=response.data["id"])
    assert printer.makerspace == makerspace

    response = client.post(
        spool_list_url(),
        {
            "makerspace": makerspace.id,
            "printer": printer.id,
            "material": "PLA",
            "color": "black",
            "brand": "Generic",
            "initial_weight_grams": "1000.00",
            "remaining_weight_grams": "850.00",
        },
        format="json",
    )

    assert response.status_code == 201
    spool = FilamentSpool.objects.get(pk=response.data["id"])
    assert spool.printer == printer
    assert spool.remaining_weight_grams == 850

    response = client.post(
        printer_list_url(),
        {"makerspace": other_space.id, "name": "Other printer"},
        format="json",
    )
    assert response.status_code == 400

    response = authenticated_client(guest).post(
        printer_list_url(),
        {"makerspace": makerspace.id, "name": "Guest printer"},
        format="json",
    )
    assert response.status_code == 403


def test_printer_list_shows_free_state_pending_minutes_and_spool_leftover_estimate():
    makerspace = make_space("printer-estimates")
    bucket = make_bucket(makerspace)
    requester = make_user("printer-estimate-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("printer-estimate-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PETG",
        color="orange",
        initial_weight_grams=1000,
        remaining_weight_grams=640,
    )
    first = make_request(bucket, requester, title="Active", status=PrintRequest.Status.ACCEPTED)
    second = make_request(bucket, requester, title="Queued", status=PrintRequest.Status.ACCEPTED)
    second.printer = printer
    second.filament_spool = spool
    second.estimated_minutes = 45
    second.estimated_filament_grams = 80
    second.save(
        update_fields=[
            "printer",
            "filament_spool",
            "estimated_minutes",
            "estimated_filament_grams",
            "updated_at",
        ]
    )

    response = authenticated_client(manager).post(
        action_url(first, "start"),
        {
            "printer_id": printer.id,
            "filament_spool_id": spool.id,
            "estimated_minutes": 120,
            "estimated_filament_grams": "150.00",
        },
        format="json",
    )
    assert response.status_code == 200

    response = authenticated_client(manager).get(
        printer_list_url(), {"makerspace": makerspace.id}
    )

    assert response.status_code == 200
    row = response.data["results"][0]
    assert row["is_free"] is False
    assert row["current_request"]["id"] == first.id
    assert row["pending_estimated_minutes"] == 165
    assert row["active_spool"]["id"] == spool.id
    assert row["active_spool"]["remaining_weight_grams"] == "490.00"
    assert row["estimated_spool_remaining_after_queue_grams"] == "410.00"


def test_start_rejects_busy_printer_and_cross_space_spool():
    makerspace = make_space("printer-busy")
    other_space = make_space("printer-busy-other")
    bucket = make_bucket(makerspace)
    other_printer = PrintPrinter.objects.create(makerspace=other_space, name="Other")
    requester = make_user("busy-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("busy-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Busy")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        initial_weight_grams=1000,
        remaining_weight_grams=100,
    )
    active = make_request(bucket, requester, title="Running", status=PrintRequest.Status.PRINTING)
    active.printer = printer
    active.filament_spool = spool
    active.save(update_fields=["printer", "filament_spool", "updated_at"])
    next_request = make_request(bucket, requester, title="Next", status=PrintRequest.Status.ACCEPTED)

    response = authenticated_client(manager).post(
        action_url(next_request, "start"),
        {"printer_id": printer.id},
        format="json",
    )
    assert response.status_code == 409

    response = authenticated_client(manager).post(
        action_url(next_request, "start"),
        {"printer_id": other_printer.id},
        format="json",
    )
    assert response.status_code == 409


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

    # 4 = 2 sends (requester + staff) x async double-on_commit (queue hook -> dispatch enqueue hook).
    assert len(callbacks) == 4
    assert len(mail.outbox) == 2
    assert ["reject-requester@e.com"] in [message.to for message in mail.outbox]
    assert ["reject-manager@e.com"] in [message.to for message in mail.outbox]
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.REJECTED
    assert print_request.reason == "Model needs supports clarified."
    assert AuditLog.objects.get(action="print.rejected").target_id == str(print_request.id)


def test_print_manager_fails_printing_request_no_requester_email_notifies_staff(
    django_capture_on_commit_callbacks,
):
    # Failing a print must NEVER email the requester (unchanged contract), but the new
    # staff-notification feature DOES alert the makerspace's print staff. Execute the
    # on_commit callbacks so the assertion reflects real delivery, not just the sync path.
    makerspace = make_space("fail-flow")
    bucket = make_bucket(makerspace)
    requester = make_user("fail-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("fail-manager", makerspace)
    print_request = make_request(
        bucket,
        requester,
        status=PrintRequest.Status.PRINTING,
    )
    print_request.contact_email = "fail-buyer@example.com"
    print_request.save(update_fields=["contact_email", "updated_at"])
    reset_outbox()

    with django_capture_on_commit_callbacks(execute=True):
        response = authenticated_client(manager).post(
            action_url(print_request, "fail"),
            {"reason": "Nozzle jammed.", "percent_complete": 0},
            format="json",
        )

    assert response.status_code == 200
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.FAILED
    assert print_request.reason == "Nozzle jammed."
    assert AuditLog.objects.get(action="print.failed").target_id == str(print_request.id)
    recipients = [address for message in mail.outbox for address in message.to]
    # No requester-facing email on failure.
    assert "fail-buyer@example.com" not in recipients
    assert requester.email not in recipients
    # Staff (the print manager) are notified of the failure.
    assert manager.email in recipients


def test_print_manager_fail_requires_percent_complete():
    makerspace = make_space("fail-percent-required")
    bucket = make_bucket(makerspace)
    requester = make_user("fail-percent-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("fail-percent-manager", makerspace)
    print_request = make_request(
        bucket,
        requester,
        status=PrintRequest.Status.PRINTING,
    )

    response = authenticated_client(manager).post(
        action_url(print_request, "fail"),
        {"reason": "Nozzle jammed."},
        format="json",
    )

    assert response.status_code == 400
    assert "percent_complete" in response.data
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.PRINTING


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


def test_superadmin_managed_print_list_hides_disabled_space_unless_explicit():
    visible_space = make_space("manage-visible-superadmin")
    hidden_space = make_space("manage-hidden-superadmin")
    make_member("manage-hidden-superadmin-manager", hidden_space)
    hidden_space.superadmin_access_enabled = False
    hidden_space.save(update_fields=["superadmin_access_enabled"])
    visible_bucket = make_bucket(visible_space)
    hidden_bucket = make_bucket(hidden_space)
    requester = make_user(
        "manage-hidden-superadmin-requester",
        access_status=User.AccessStatus.ACTIVE,
    )
    visible_request = make_request(visible_bucket, requester, title="Visible")
    hidden_request = make_request(hidden_bucket, requester, title="Hidden")
    superadmin = make_user(
        "manage-hidden-superadmin",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )
    client = authenticated_client(superadmin)

    response = client.get(managed_list_url())
    assert response.status_code == 200
    assert result_ids(response) == {visible_request.id}

    # Hard hide: an explicit ?makerspace=<hidden id> is FORBIDDEN (403) for a
    # global superadmin (CanManagePrinting denies the disabled space; the soft-hide
    # escape hatch is closed by the RBAC block).
    response = client.get(managed_list_url(), {"makerspace": hidden_space.id})
    assert response.status_code == 403


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
    django_capture_on_commit_callbacks,
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

    # Email delivery is async (dispatch_email -> on_commit -> Celery task); fire the
    # commit hooks so the eager task actually sends.
    with django_capture_on_commit_callbacks(execute=True):
        send_print_email(event, print_request)

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.subject
    assert len(message.alternatives) == 1
    html, mimetype = message.alternatives[0]
    assert mimetype == "text/html"
    assert "Makerspace" in html
    assert "background:#111111;color:#FBB905" in html


def test_printbucket_admin_changelist_is_superadmin_only():
    managed = make_space("admin-managed")
    other = make_space("admin-other")
    manager = make_member(
        "print-admin-manager",
        managed,
        membership_role=MakerspaceMembership.Role.PRINT_MANAGER,
        role=User.Role.REQUESTER,
    )
    manager.is_staff = True
    manager.save(update_fields=["is_staff"])
    superadmin = make_user(
        "print-admin-superadmin",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
        is_staff=True,
        is_superuser=True,
    )
    make_bucket(managed, name="In scope")
    make_bucket(other, name="Out of scope")
    url = reverse("admin:printing_printbucket_changelist")

    client = Client()
    client.force_login(manager)
    assert client.get(url).status_code == 403

    client.force_login(superadmin)
    assert client.get(url).status_code == 200
