from decimal import Decimal
from unittest.mock import Mock

from django.contrib import admin
from django.test import RequestFactory

import pytest
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.makerspaces import lifecycle
from apps.printing.models import ManualPrintLog, PrintPrinter, PrintRequest
from apps.printing.reports import build_printing_report
from apps.inventory.public_stats import build_public_stats
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


def printer_image_url(printer):
    return reverse("admin-printer-image", kwargs={"pk": printer.id})


def printer_detail_url(printer):
    return reverse("printing:managed-printer-detail", kwargs={"pk": printer.id})


def mock_public_storage(monkeypatch, *, size=123):
    monkeypatch.setattr(
        "apps.inventory.public_image_storage.presigned_upload",
        lambda object_key, content_type: {
            "url": "http://minio/public-upload",
            "fields": {"key": object_key, "Content-Type": content_type},
        },
    )
    monkeypatch.setattr("apps.inventory.public_image_storage.finalize_upload", lambda object_key: size)
    delete = Mock()
    monkeypatch.setattr("apps.inventory.public_image_storage.delete_object", delete)
    return delete


def test_printer_image_upload_attach_clear(monkeypatch, settings):
    settings.PUBLIC_IMAGE_BASE_URL = "http://cdn.test/public-images"
    delete = mock_public_storage(monkeypatch)
    makerspace = make_space("printer-image-attach")
    manager = make_print_manager("printer-image-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")
    client = authenticated_client(manager)

    upload = client.post(
        printer_image_url(printer),
        {"content_type": "image/png", "filename": "mk4.png"},
        format="json",
    )
    object_key = upload.data["object_key"]
    attached = client.put(printer_image_url(printer), {"object_key": object_key}, format="json")
    cleared = client.delete(printer_image_url(printer))

    assert upload.status_code == 201
    assert object_key.startswith(f"printers/{makerspace.id}/")
    assert attached.status_code == 200
    assert attached.data["image_url"] == f"http://cdn.test/public-images/{object_key}"
    assert "image_key" not in attached.data
    printer.refresh_from_db()
    assert printer.image_key == ""
    assert cleared.status_code == 200
    assert cleared.data["image_url"] is None
    delete.assert_called_once_with(object_key)
    assert AuditLog.objects.filter(action="printing.printer_image_attached").exists()
    assert AuditLog.objects.filter(action="printing.printer_image_cleared").exists()


def test_printer_image_replaces_old_key(monkeypatch):
    delete = mock_public_storage(monkeypatch)
    makerspace = make_space("printer-image-replace")
    manager = make_print_manager("printer-image-replace-manager", makerspace)
    printer = PrintPrinter.objects.create(
        makerspace=makerspace,
        name="Voron",
        image_key=f"printers/{makerspace.id}/old.png",
    )
    new_key = f"printers/{makerspace.id}/new.png"

    response = authenticated_client(manager).put(
        printer_image_url(printer),
        {"object_key": new_key},
        format="json",
    )

    assert response.status_code == 200
    printer.refresh_from_db()
    assert printer.image_key == new_key
    delete.assert_called_once_with(f"printers/{makerspace.id}/old.png")


def test_printer_image_scope_and_prefix_guard(monkeypatch):
    mock_public_storage(monkeypatch)
    own_space = make_space("printer-image-own")
    other_space = make_space("printer-image-other")
    manager = make_print_manager("printer-image-scope-manager", own_space)
    own_printer = PrintPrinter.objects.create(makerspace=own_space, name="Own")
    other_printer = PrintPrinter.objects.create(makerspace=other_space, name="Other")
    guest = make_member("printer-image-guest", own_space)

    cross_scope = authenticated_client(manager).post(
        printer_image_url(other_printer),
        {"content_type": "image/png", "filename": "other.png"},
        format="json",
    )
    bad_prefix = authenticated_client(manager).put(
        printer_image_url(own_printer),
        {"object_key": f"printers/{other_space.id}/not-yours.png"},
        format="json",
    )
    space_manager_allowed = authenticated_client(guest).post(
        printer_image_url(own_printer),
        {"content_type": "image/png", "filename": "own.png"},
        format="json",
    )

    assert cross_scope.status_code == 404
    assert bad_prefix.status_code == 400
    assert space_manager_allowed.status_code == 201
    own_printer.refresh_from_db()
    assert own_printer.image_key == ""


@pytest.mark.django_db(transaction=True)
def test_purge_deletes_printer_image(monkeypatch):
    actor = make_user(
        "printer-image-purge-super",
        role="superadmin",
        access_status="active",
        is_staff=True,
        is_superuser=True,
    )
    makerspace = make_space("printer-image-purge")
    printer = PrintPrinter.objects.create(
        makerspace=makerspace,
        name="Purge printer",
        image_key=f"printers/{makerspace.id}/printer.png",
    )
    deleted = []
    monkeypatch.setattr(lifecycle, "_delete_storage_keys", lambda keys: None)
    monkeypatch.setattr(
        "apps.inventory.public_image_storage.delete_object",
        lambda key: deleted.append(key),
    )

    archived = lifecycle.archive(makerspace, actor)
    lifecycle.purge(archived, actor)

    assert printer.image_key in deleted
    assert not PrintPrinter.objects.filter(pk=printer.pk).exists()


def test_printer_delete_deletes_image_object(monkeypatch):
    delete = mock_public_storage(monkeypatch)
    makerspace = make_space("printer-image-delete")
    manager = make_print_manager("printer-image-delete-manager", makerspace)
    printer = PrintPrinter.objects.create(
        makerspace=makerspace,
        name="Delete printer",
        image_key=f"printers/{makerspace.id}/delete.png",
    )

    response = authenticated_client(manager).delete(printer_detail_url(printer))

    assert response.status_code == 204
    delete.assert_called_once_with(f"printers/{makerspace.id}/delete.png")

def test_printer_makerspace_move_clears_image_key():
    source = make_space("printer-image-move-source")
    dest = make_space("printer-image-move-dest")
    superadmin = make_user(
        "printer-image-move-super",
        role="superadmin",
        access_status="active",
        is_staff=True,
        is_superuser=True,
    )
    printer = PrintPrinter.objects.create(
        makerspace=source,
        name="Movable printer",
        image_key=f"printers/{source.id}/stale.png",
    )

    response = authenticated_client(superadmin).patch(
        printer_detail_url(printer),
        {"makerspace": dest.id},
        format="json",
    )

    assert response.status_code == 200
    printer.refresh_from_db()
    assert printer.makerspace_id == dest.id
    assert printer.image_key == ""
    assert response.data["image_url"] is None


def test_printer_admin_makerspace_move_clears_image_key():
    source = make_space("printer-admin-image-move-source")
    dest = make_space("printer-admin-image-move-dest")
    superadmin = make_user(
        "printer-admin-image-move-super",
        role="superadmin",
        access_status="active",
        is_staff=True,
        is_superuser=True,
    )
    printer = PrintPrinter.objects.create(
        makerspace=source,
        name="Admin moved printer",
        image_key=f"printers/{source.id}/stale.png",
    )
    request = RequestFactory().post("/control/printing/printprinter/")
    request.user = superadmin
    form = Mock(cleaned_data={"image_upload": None, "clear_image": False})

    printer.makerspace = dest
    admin.site._registry[PrintPrinter].save_model(request, printer, form, change=True)

    printer.refresh_from_db()
    assert printer.makerspace_id == dest.id
    assert printer.image_key == ""


def test_report_and_public_stats_include_printer_image_url(settings):
    settings.PUBLIC_IMAGE_BASE_URL = "http://cdn.test/public-images"
    makerspace = make_space("printer-image-report")
    bucket = make_bucket(makerspace)
    requester = make_user("printer-image-report-requester", access_status="active")
    printer = PrintPrinter.objects.create(
        makerspace=makerspace,
        name="Report printer",
        image_key=f"printers/{makerspace.id}/report.png",
    )
    PrintRequest.objects.create(
        bucket=bucket,
        requester=requester,
        title="Completed print",
        status=PrintRequest.Status.COMPLETED,
        printer=printer,
        estimated_minutes=60,
        filament_grams_used=Decimal("20.00"),
    )
    ManualPrintLog.objects.create(
        makerspace=makerspace,
        printer=printer,
        grams_used=Decimal("5.00"),
        duration_minutes=30,
        title="Manual print",
    )

    report = build_printing_report(makerspace.id)
    stats = build_public_stats(makerspace)
    expected = f"http://cdn.test/public-images/{printer.image_key}"

    assert report["printer_hours"][0]["image_url"] == expected
    assert report["printer_outcomes"][0]["image_url"] == expected
    assert stats["printing"]["busiest_printer"]["image_url"] == expected
    assert stats["printing"]["per_printer"][0]["image_url"] == expected
