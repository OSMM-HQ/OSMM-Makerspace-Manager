from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.makerspaces.models import MakerspaceMembership
from apps.printing.models import FilamentSpool, PrintPrinter, PrintRequest, PrintRequestFile
from tests.test_printing import (
    authenticated_client,
    make_bucket,
    make_member,
    make_print_manager,
    make_request,
    make_space,
    make_user,
)

pytestmark = pytest.mark.django_db


def printer_list_url():
    return reverse("printing:managed-printer-list")


def printer_detail_url(printer):
    return reverse("printing:managed-printer-detail", kwargs={"pk": printer.id})


def spool_list_url():
    return reverse("printing:managed-spool-list")


def spool_detail_url(spool):
    return reverse("printing:managed-spool-detail", kwargs={"pk": spool.id})


def action_url(print_request, action):
    return reverse(f"printing:managed-request-{action}", kwargs={"pk": print_request.id})


def managed_file_url(print_file):
    return reverse("printing:managed-file-url", kwargs={"pk": print_file.id})


def test_managed_file_url_returns_signed_url_for_owner_makerspace(monkeypatch):
    makerspace = make_space("manage-file-url-own")
    bucket = make_bucket(makerspace)
    requester = make_user("manage-file-url-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("manage-file-url-manager", makerspace)
    print_request = make_request(bucket, requester)
    print_file = PrintRequestFile.objects.create(
        print_request=print_request,
        makerspace=makerspace,
        kind=PrintRequestFile.Kind.STL,
        object_key="printing/manage-file-url-own/model.stl",
        content_type="model/stl",
        original_filename="model.stl",
        size_bytes=1234,
        owner_checkin_user_id="x",
    )
    captured = {}

    def fake(object_key, **kwargs):
        captured["object_key"] = object_key
        captured.update(kwargs)
        return "http://signed/url"

    monkeypatch.setattr("apps.printing.views_requests.print_get_url", fake)

    response = authenticated_client(manager).get(managed_file_url(print_file))

    assert response.status_code == 200
    assert response.data["url"] == "http://signed/url"
    assert captured["object_key"] == print_file.object_key
    assert captured["as_attachment"] is True
    assert captured["filename"] == "model.stl"
    assert captured["content_type"] == "model/stl"


def test_managed_file_url_screenshot_is_inline(monkeypatch):
    makerspace = make_space("manage-file-url-screenshot")
    bucket = make_bucket(makerspace)
    requester = make_user("manage-file-url-shot-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("manage-file-url-shot-manager", makerspace)
    print_request = make_request(bucket, requester)
    print_file = PrintRequestFile.objects.create(
        print_request=print_request,
        makerspace=makerspace,
        kind=PrintRequestFile.Kind.SCREENSHOT,
        object_key="printing/manage-file-url-screenshot/preview.png",
        content_type="image/png",
        original_filename="preview.png",
        size_bytes=1234,
        owner_checkin_user_id="x",
    )
    captured = {}

    def fake(object_key, **kwargs):
        captured["object_key"] = object_key
        captured.update(kwargs)
        return "http://signed/screenshot"

    monkeypatch.setattr("apps.printing.views_requests.print_get_url", fake)

    response = authenticated_client(manager).get(managed_file_url(print_file))

    assert response.status_code == 200
    assert response.data["url"] == "http://signed/screenshot"
    assert captured["object_key"] == print_file.object_key
    assert captured["as_attachment"] is False
    assert captured["filename"] == "preview.png"
    assert captured["content_type"] == "image/png"


def test_managed_file_url_rejects_unattached_staging_file():
    makerspace = make_space("manage-file-url-unattached")
    manager = make_print_manager("manage-file-url-unattached-manager", makerspace)
    staged = PrintRequestFile.objects.create(
        makerspace=makerspace,
        kind=PrintRequestFile.Kind.STL,
        object_key="printing/manage-file-url-unattached/staged.stl",
        owner_checkin_user_id="x",
    )

    response = authenticated_client(manager).get(managed_file_url(staged))

    assert response.status_code == 404


def test_managed_file_url_out_of_scope_404():
    makerspace = make_space("manage-file-url-own-scope")
    other_space = make_space("manage-file-url-other-scope")
    other_bucket = make_bucket(other_space)
    requester = make_user("manage-file-url-scope-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("manage-file-url-scope-manager", makerspace)
    print_request = make_request(other_bucket, requester)
    print_file = PrintRequestFile.objects.create(
        print_request=print_request,
        makerspace=other_space,
        kind=PrintRequestFile.Kind.STL,
        object_key="printing/manage-file-url-other/model.stl",
        owner_checkin_user_id="x",
    )

    response = authenticated_client(manager).get(managed_file_url(print_file))

    assert response.status_code == 404


def test_managed_printer_create_success_and_validation_error():
    makerspace = make_space("manage-printer-create")
    manager = make_print_manager("manage-printer-create-manager", makerspace)
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
    assert printer.name == "Bambu A1"

    response = client.post(
        printer_list_url(),
        {"makerspace": makerspace.id, "name": "", "status": "active"},
        format="json",
    )

    assert response.status_code == 400
    assert "name" in response.data


def test_managed_spool_create_and_remaining_weight_adjustment():
    makerspace = make_space("manage-spool-create")
    manager = make_print_manager("manage-spool-create-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")
    client = authenticated_client(manager)

    response = client.post(
        spool_list_url(),
        {
            "makerspace": makerspace.id,
            "printer": printer.id,
            "material": "PLA",
            "color": "black",
            "brand": "Generic",
            "initial_weight_grams": "1000.00",
            "remaining_weight_grams": "900.00",
        },
        format="json",
    )

    assert response.status_code == 201
    spool = FilamentSpool.objects.get(pk=response.data["id"])
    assert spool.printer == printer
    assert spool.remaining_weight_grams == Decimal("900.00")

    response = client.patch(
        spool_detail_url(spool),
        {"remaining_weight_grams": "750.00"},
        format="json",
    )

    assert response.status_code == 200
    spool.refresh_from_db()
    assert spool.remaining_weight_grams == Decimal("750.00")

    response = client.patch(
        spool_detail_url(spool),
        {"remaining_weight_grams": "1200.00"},
        format="json",
    )

    assert response.status_code == 400
    assert "remaining_weight_grams" in response.data


def test_managed_fail_print_requires_reason_and_stores_reason():
    makerspace = make_space("manage-fail-print")
    bucket = make_bucket(makerspace)
    requester = make_user("manage-fail-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("manage-fail-manager", makerspace)
    print_request = make_request(
        bucket,
        requester,
        status=PrintRequest.Status.PRINTING,
    )

    response = authenticated_client(manager).post(
        action_url(print_request, "fail"),
        {"reason": "Layer shift.", "percent_complete": 0},
        format="json",
    )

    assert response.status_code == 200
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.FAILED
    assert print_request.reason == "Layer shift."


def test_managed_spool_delete_removes_unreferenced_spool():
    makerspace = make_space("manage-spool-del-ok")
    manager = make_print_manager("manage-spool-del-ok-manager", makerspace)
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        material="PLA",
        initial_weight_grams=1000,
        remaining_weight_grams=1000,
    )

    response = authenticated_client(manager).delete(spool_detail_url(spool))

    assert response.status_code == 204
    assert not FilamentSpool.objects.filter(pk=spool.id).exists()


def test_managed_printer_delete_removes_unreferenced_printer():
    makerspace = make_space("manage-printer-del-ok")
    manager = make_print_manager("manage-printer-del-ok-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")

    response = authenticated_client(manager).delete(printer_detail_url(printer))

    assert response.status_code == 204
    assert not PrintPrinter.objects.filter(pk=printer.id).exists()


def test_managed_printer_delete_clears_request_reference_keeps_history():
    makerspace = make_space("manage-printer-del-ref")
    bucket = make_bucket(makerspace)
    requester = make_user("manage-printer-del-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("manage-printer-del-ref-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")
    print_request = make_request(bucket, requester)
    print_request.printer = printer
    print_request.save(update_fields=["printer"])

    response = authenticated_client(manager).delete(printer_detail_url(printer))

    # Hard-delete succeeds; the request row survives with its printer FK cleared
    # (on_delete=SET_NULL), so print history is preserved.
    assert response.status_code == 204
    assert not PrintPrinter.objects.filter(pk=printer.id).exists()
    print_request.refresh_from_db()
    assert print_request.printer_id is None


def test_managed_printer_delete_blocks_in_progress_job_with_409():
    makerspace = make_space("manage-printer-del-active")
    bucket = make_bucket(makerspace)
    requester = make_user("manage-printer-del-active-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("manage-printer-del-active-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")
    print_request = make_request(bucket, requester, status=PrintRequest.Status.PRINTING)
    print_request.printer = printer
    print_request.save(update_fields=["printer"])

    response = authenticated_client(manager).delete(printer_detail_url(printer))

    # A printer running a job keeps attribution: delete is refused until the job ends.
    assert response.status_code == 409
    assert PrintPrinter.objects.filter(pk=printer.id).exists()


def test_managed_printer_delete_clears_spool_reference_keeps_history():
    makerspace = make_space("manage-printer-del-spool")
    manager = make_print_manager("manage-printer-del-spool-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PETG",
        initial_weight_grams=1000,
        remaining_weight_grams=1000,
    )

    response = authenticated_client(manager).delete(printer_detail_url(printer))

    assert response.status_code == 204
    assert not PrintPrinter.objects.filter(pk=printer.id).exists()
    spool.refresh_from_db()
    assert spool.printer_id is None


def test_managed_spool_delete_blocks_referenced_spool_with_409():
    makerspace = make_space("manage-spool-del-ref")
    bucket = make_bucket(makerspace)
    requester = make_user("manage-spool-del-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("manage-spool-del-ref-manager", makerspace)
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        material="PLA",
        initial_weight_grams=1000,
        remaining_weight_grams=600,
    )
    print_request = make_request(bucket, requester)
    print_request.filament_spool = spool
    print_request.save(update_fields=["filament_spool"])

    response = authenticated_client(manager).delete(spool_detail_url(spool))

    assert response.status_code == 409
    assert FilamentSpool.objects.filter(pk=spool.id).exists()


def test_managed_spool_delete_out_of_scope_returns_404():
    makerspace = make_space("manage-spool-del-own")
    other_space = make_space("manage-spool-del-other")
    manager = make_print_manager("manage-spool-del-scope-manager", makerspace)
    other_spool = FilamentSpool.objects.create(
        makerspace=other_space,
        material="PLA",
        initial_weight_grams=1000,
        remaining_weight_grams=1000,
    )

    response = authenticated_client(manager).delete(spool_detail_url(other_spool))

    assert response.status_code == 404
    assert FilamentSpool.objects.filter(pk=other_spool.id).exists()


def test_managed_edit_deactivate_is_rbac_scoped_to_makerspace():
    makerspace = make_space("manage-edit-own")
    other_space = make_space("manage-edit-other")
    manager = make_print_manager("manage-edit-manager", makerspace)
    guest = make_member(
        "manage-edit-guest",
        makerspace,
        membership_role=MakerspaceMembership.Role.GUEST_ADMIN,
        role=User.Role.GUEST_ADMIN,
    )
    own_printer = PrintPrinter.objects.create(makerspace=makerspace, name="Own")
    other_printer = PrintPrinter.objects.create(makerspace=other_space, name="Other")
    own_spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=own_printer,
        material="PETG",
        initial_weight_grams=1000,
        remaining_weight_grams=800,
    )
    client = authenticated_client(manager)

    response = client.patch(
        printer_detail_url(own_printer),
        {"model": "MK4S", "status": "maintenance"},
        format="json",
    )
    assert response.status_code == 200
    own_printer.refresh_from_db()
    assert own_printer.model == "MK4S"
    assert own_printer.status == PrintPrinter.Status.MAINTENANCE

    response = client.patch(
        printer_detail_url(own_printer),
        {"is_active": False},
        format="json",
    )
    assert response.status_code == 200
    own_printer.refresh_from_db()
    assert own_printer.is_active is False

    response = client.patch(
        spool_detail_url(own_spool),
        {"is_active": False},
        format="json",
    )
    assert response.status_code == 200
    own_spool.refresh_from_db()
    assert own_spool.is_active is False

    response = client.patch(
        printer_detail_url(other_printer),
        {"model": "Out of scope"},
        format="json",
    )
    assert response.status_code == 404

    response = authenticated_client(guest).patch(
        printer_detail_url(own_printer),
        {"model": "Guest update"},
        format="json",
    )
    assert response.status_code == 403


def test_managed_print_request_exposes_original_approver_after_later_action():
    makerspace = make_space("manage-print-approver")
    bucket = make_bucket(makerspace)
    requester = make_user("manage-print-approver-requester", access_status=User.AccessStatus.ACTIVE)
    approver = make_print_manager("manage-print-approver-one", makerspace)
    starter = make_print_manager("manage-print-approver-two", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Approver Printer")
    spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=printer,
        material="PLA",
        initial_weight_grams=1000,
        remaining_weight_grams=1000,
    )
    print_request = make_request(bucket, requester)

    accepted = authenticated_client(approver).post(
        action_url(print_request, "accept"),
        {"price": "0"},
        format="json",
    )
    started = authenticated_client(starter).post(
        action_url(print_request, "start"),
        {
            "printer_id": printer.id,
            "filament_spool_id": spool.id,
            "estimated_minutes": 30,
            "estimated_filament_grams": "20.00",
        },
        format="json",
    )
    detail = authenticated_client(starter).get(
        reverse("printing:managed-request-detail", kwargs={"pk": print_request.id})
    )

    assert accepted.status_code == 200
    assert accepted.data["accepted_by"]["username"] == approver.username
    assert started.status_code == 200
    assert started.data["handled_by"] == starter.id
    assert started.data["accepted_by"]["username"] == approver.username
    assert detail.status_code == 200
    assert detail.data["accepted_by"] == {
        "username": approver.username,
        "role": approver.role,
    }
