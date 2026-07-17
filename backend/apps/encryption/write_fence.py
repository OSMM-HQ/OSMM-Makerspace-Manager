"""Persistent, advisory-lock-backed guard for every mapped PII write."""

from contextlib import contextmanager
from uuid import uuid4

from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from apps.audit.services import record
from apps.accounts.models import User
from apps.encryption.models import PiiGlobalWriteFence, PiiMakerspaceWriteFence

GLOBAL_LOCK_NAMESPACE = 734_201
TENANT_LOCK_NAMESPACE = 734_202


class PiiWriteFenced(Exception):
    """A mapped write was refused by the persistent database fence."""


def _execute_lock(cursor, function, *values):
    cursor.execute(f"SELECT {function}(%s, %s)", [*values])


def assert_mapped_write_allowed(makerspace_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pii_assert_mapped_write_allowed(%s)", [makerspace_id])
    except DatabaseError as exc:
        if "pii write fence" in str(exc).lower():
            raise PiiWriteFenced("Protected writes are temporarily unavailable.") from exc
        raise


@contextmanager
def fence_operation(operation_id):
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL app.pii_fence_operation = %s", [str(operation_id)])
    yield


def _close_rows(rows, operation_kind, actor_id, *, makerspace=None):
    if any(row.state == row.State.CLOSED for row in rows):
        raise PiiWriteFenced("PII write fence is already closed.")
    operation_id, now = uuid4(), timezone.now()
    actor = User.objects.get(pk=actor_id)
    for row in rows:
        row.state = row.State.CLOSED
        row.operation_id = operation_id
        row.operation_kind = operation_kind
        row.actor_id = actor_id
        row.closed_at = now
        row.opened_at = None
        row.save(update_fields=["state", "operation_id", "operation_kind", "actor_id", "closed_at", "opened_at"])
        record(
            actor,
            "encryption.write_fence_closed",
            makerspace=row.makerspace if hasattr(row, "makerspace") else makerspace,
            target=row,
            meta={"operation_id": str(operation_id), "operation_kind": operation_kind, "actor_id": actor_id},
        )
    return operation_id


def close_global(operation_kind, actor_id, *, all_makerspaces=False):
    with transaction.atomic(), connection.cursor() as cursor:
        _execute_lock(cursor, "pg_advisory_xact_lock", GLOBAL_LOCK_NAMESPACE, 0)
        global_fence = PiiGlobalWriteFence.objects.select_for_update().get(pk=1)
        rows = [global_fence]
        if all_makerspaces:
            tenant_ids = list(
                PiiMakerspaceWriteFence.objects.order_by("makerspace_id").values_list("makerspace_id", flat=True)
            )
            for makerspace_id in tenant_ids:
                _execute_lock(cursor, "pg_advisory_xact_lock", TENANT_LOCK_NAMESPACE, makerspace_id)
            tenants = list(PiiMakerspaceWriteFence.objects.select_for_update().filter(makerspace_id__in=tenant_ids).order_by("makerspace_id"))
            rows.extend(tenants)
        return _close_rows(rows, operation_kind, actor_id)


def close_makerspace(makerspace_id, operation_kind, actor_id):
    with transaction.atomic(), connection.cursor() as cursor:
        _execute_lock(cursor, "pg_advisory_xact_lock_shared", GLOBAL_LOCK_NAMESPACE, 0)
        _execute_lock(cursor, "pg_advisory_xact_lock", TENANT_LOCK_NAMESPACE, makerspace_id)
        fence = PiiMakerspaceWriteFence.objects.select_for_update().get(makerspace_id=makerspace_id)
        return _close_rows([fence], operation_kind, actor_id)


def reopen(operation_id, actor_id):
    with transaction.atomic(), connection.cursor() as cursor:
        global_fence = PiiGlobalWriteFence.objects.filter(operation_id=operation_id).first()
        if global_fence is not None:
            _execute_lock(cursor, "pg_advisory_xact_lock", GLOBAL_LOCK_NAMESPACE, 0)
            global_fence = PiiGlobalWriteFence.objects.select_for_update().get(pk=1)
            rows = [global_fence]
            tenants = list(PiiMakerspaceWriteFence.objects.filter(operation_id=operation_id).select_for_update().order_by("makerspace_id"))
            for fence in tenants:
                _execute_lock(cursor, "pg_advisory_xact_lock", TENANT_LOCK_NAMESPACE, fence.makerspace_id)
            rows.extend(tenants)
        else:
            fence = PiiMakerspaceWriteFence.objects.filter(operation_id=operation_id).first()
            if fence is None:
                raise PiiWriteFenced("No closed PII write fence matches this operation.")
            _execute_lock(cursor, "pg_advisory_xact_lock_shared", GLOBAL_LOCK_NAMESPACE, 0)
            _execute_lock(cursor, "pg_advisory_xact_lock", TENANT_LOCK_NAMESPACE, fence.makerspace_id)
            rows = [PiiMakerspaceWriteFence.objects.select_for_update().get(pk=fence.pk)]
        if any(row.state != row.State.CLOSED or row.operation_id != operation_id for row in rows):
            raise PiiWriteFenced("No closed PII write fence matches this operation.")
        now = timezone.now()
        actor = User.objects.get(pk=actor_id)
        for row in rows:
            row.state = row.State.OPEN
            row.operation_id = None
            row.operation_kind = None
            row.actor_id = actor_id
            row.opened_at = now
            row.save(update_fields=["state", "operation_id", "operation_kind", "actor_id", "opened_at"])
            record(
                actor,
                "encryption.write_fence_opened",
                makerspace=row.makerspace if hasattr(row, "makerspace") else None,
                target=row,
                meta={"operation_id": str(operation_id), "actor_id": actor_id},
            )
        return rows
