from decimal import Decimal

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError

from apps.maintenance.models import (
    MaintenanceLog,
    MaintenanceLogDocument,
    MaintenanceLogImmutableError,
    MaintenanceSchedule,
)
from tests.maintenance.helpers import make_machine_setup
from tests.return_helpers import make_user


pytestmark = pytest.mark.django_db


def test_schedule_and_log_constraints_and_ordering():
    _, manager, machine, _ = make_machine_setup("maintenance-models")
    first = MaintenanceSchedule.objects.create(
        machine=machine, description="Later", interval_days=30,
        next_due="2026-08-01", created_by=manager,
    )
    second = MaintenanceSchedule.objects.create(
        machine=machine, description="Sooner", interval_days=7,
        next_due="2026-07-20", created_by=manager,
    )
    newest = MaintenanceLog.objects.create(
        machine=machine, performed_by=manager, summary="Newest",
        cost=Decimal("12.50"),
    )
    older = MaintenanceLog.objects.create(
        machine=machine, performed_by=manager, summary="Older",
        performed_at="2026-01-01T00:00:00Z",
    )

    assert list(MaintenanceSchedule.objects.values_list("id", flat=True)) == [
        second.id, first.id,
    ]
    assert list(MaintenanceLog.objects.values_list("id", flat=True)) == [
        newest.id, older.id,
    ]
    assert newest.parts_note == ""
    with pytest.raises(IntegrityError), transaction.atomic():
        MaintenanceSchedule.objects.create(
            machine=machine, description="Bad", interval_days=0,
            next_due="2026-07-20",
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        MaintenanceLog.objects.create(
            machine=machine, summary="Bad", cost=Decimal("-0.01"),
        )


def test_log_is_append_only_at_model_and_database_layers():
    _, manager, machine, _ = make_machine_setup("maintenance-immutable")
    log = MaintenanceLog.objects.create(
        machine=machine, performed_by=manager, summary="Original",
    )

    log.summary = "Changed"
    with pytest.raises(MaintenanceLogImmutableError):
        log.save()
    with pytest.raises(MaintenanceLogImmutableError):
        log.delete()
    with pytest.raises(DatabaseError), transaction.atomic():
        MaintenanceLog.objects.filter(pk=log.pk).update(summary="Changed")
    with pytest.raises(DatabaseError), transaction.atomic():
        MaintenanceLog.objects.filter(pk=log.pk).delete()
    log.refresh_from_db()
    assert log.summary == "Original"


@pytest.mark.django_db(transaction=True)
def test_purge_guard_allows_only_delete_not_update():
    _, manager, machine, _ = make_machine_setup("maintenance-purge-guard")
    update_log = MaintenanceLog.objects.create(
        machine=machine, performed_by=manager, summary="Update blocked",
    )
    delete_log = MaintenanceLog.objects.create(
        machine=machine, performed_by=manager, summary="Delete allowed",
    )
    with pytest.raises(DatabaseError):
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.allow_immutable_delete = 'on'")
            cursor.execute(
                "UPDATE maintenance_maintenancelog SET summary=%s WHERE id=%s",
                ["mutated", update_log.id],
            )
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL app.allow_immutable_delete = 'on'")
        cursor.execute(
            "DELETE FROM maintenance_maintenancelog WHERE id=%s",
            [delete_log.id],
        )
    assert not MaintenanceLog.objects.filter(pk=delete_log.pk).exists()
    with pytest.raises(DatabaseError), transaction.atomic():
        MaintenanceLog.objects.filter(pk=update_log.pk).delete()


def test_performer_is_protected_and_document_metadata_is_required():
    _, manager, machine, _ = make_machine_setup("maintenance-protect")
    log = MaintenanceLog.objects.create(
        machine=machine, performed_by=manager, summary="Protected",
    )
    with pytest.raises(ProtectedError):
        manager.delete()
    document = MaintenanceLogDocument.objects.create(
        log=log, object_key="machines/1/1/logs/a.pdf", size_bytes=123,
    )
    assert document.size_bytes == 123
    with pytest.raises(IntegrityError), transaction.atomic():
        MaintenanceLogDocument.objects.create(
            log=log, object_key=document.object_key, size_bytes=1,
        )

