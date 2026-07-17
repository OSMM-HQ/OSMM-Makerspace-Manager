"""Focused staged-rollout rehearsal; fence primitives have fuller unit coverage elsewhere."""

import uuid

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, models, transaction
from django.test import override_settings

from apps.encryption.crypto import is_envelope
from apps.encryption.models import PiiBlindIndex
from apps.encryption.write_fence import PiiWriteFenced, close_global, reopen
from apps.hardware_requests.models import HardwareRequest
from apps.integrations.models import EmailLog
from apps.makerspaces.models import Makerspace
from tests.encryption.conftest import enabled_encryption

pytestmark = pytest.mark.django_db


def _request(name="Rollout"):
    stamp = uuid.uuid4().hex[:8]
    space = Makerspace.objects.create(name=f"Rollout {stamp}", slug=f"rollout-{stamp}")
    user = get_user_model().objects.create_user(username=f"rollout-{stamp}")
    return space, user, HardwareRequest.objects.create(
        makerspace=space, requester=user, requester_username=user.username,
        requester_name=name, requester_contact_email=f"{stamp}@example.test",
    )


def _actor():
    return get_user_model().objects.create_user(username=f"operator-{uuid.uuid4().hex[:8]}", is_active=True, is_superuser=True)


def test_flag_off_mutations_refuse_then_closed_enable_transition_redacts_platform_logs():
    space, user, row = _request()
    actor = _actor()
    log = EmailLog.objects.create(to_email="platform@example.test", subject="Legacy", text_body="body")
    with pytest.raises(CommandError):
        call_command("backfill_scoped_pii", makerspace=space.pk, model=row._meta.label)
    with enabled_encryption():
        operation = close_global("enable_transition", actor.pk, all_makerspaces=True)
        call_command("redact_platform_email_logs", apply=True, actor_id=actor.pk, fence_operation=str(operation))
        log.refresh_from_db()
        assert (log.to_email, log.subject, log.text_body) == ("", "Platform email", "")
        reopen(operation, actor.pk)


def test_decrypt_rollback_is_fenced_authenticated_resumable_and_removes_indexes():
    actor = _actor()
    with enabled_encryption():
        space, user, first = _request("First")
        second = HardwareRequest.objects.create(makerspace=space, requester=user, requester_username="second", requester_name="Second", requester_contact_email="second@example.test")
        operation = close_global("decrypt_rollback", actor.pk, all_makerspaces=True)
        call_command("decrypt_scoped_pii", makerspace=space.pk, model=first._meta.label, batch_size=1, resume_after_pk=first.pk, actor_id=actor.pk, confirm_makerspace=space.pk, fence_operation=str(operation))
        call_command("decrypt_scoped_pii", makerspace=space.pk, model=first._meta.label, batch_size=1, actor_id=actor.pk, confirm_makerspace=space.pk, fence_operation=str(operation))
        with connection.cursor() as cursor:
            cursor.execute('SELECT "requester_name" FROM "hardware_requests_hardwarerequest" WHERE id = ANY(%s)', [[first.pk, second.pk]])
            assert all(not is_envelope(value) for (value,) in cursor.fetchall())
        assert not PiiBlindIndex.objects.filter(makerspace=space).exists()
        call_command("decrypt_scoped_pii", makerspace=space.pk, model=first._meta.label, verify_only=True, actor_id=actor.pk)
        call_command("decrypt_scoped_pii", global_verify=True, verify_only=True, actor_id=actor.pk)
        reopen(operation, actor.pk)


def test_closed_global_fence_rejects_orm_bulk_and_raw_bypass_paths():
    space, user, row = _request()
    actor = _actor()
    operation = close_global("decrypt_rollback", actor.pk, all_makerspaces=True)
    with pytest.raises(PiiWriteFenced):
        HardwareRequest.objects.create(makerspace=space, requester=user, requester_username="blocked")
    clone = HardwareRequest(makerspace=space, requester=user, requester_username="bulk")
    with pytest.raises((RuntimeError, DatabaseError)), transaction.atomic():
        models.QuerySet(model=HardwareRequest).bulk_create([clone])
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute('INSERT INTO "hardware_requests_hardwarerequest" ("makerspace_id", "requester_id", "requester_username", "status", "public_token", "created_at", "updated_at") SELECT "makerspace_id", "requester_id", %s, "status", gen_random_uuid(), NOW(), NOW() FROM "hardware_requests_hardwarerequest" WHERE id = %s', ["raw", row.pk])
    reopen(operation, actor.pk)


def test_rollback_rejects_an_overflow_without_touching_source_or_index():
    actor = _actor()
    with enabled_encryption():
        space, user, row = _request("x" * 121)
        operation = close_global("decrypt_rollback", actor.pk, all_makerspaces=True)
        with pytest.raises(ValidationError):
            call_command("decrypt_scoped_pii", makerspace=space.pk, model=row._meta.label,
                         actor_id=actor.pk, confirm_makerspace=space.pk, fence_operation=str(operation))
        with connection.cursor() as cursor:
            cursor.execute('SELECT "requester_name" FROM "hardware_requests_hardwarerequest" WHERE id = %s', [row.pk])
            assert is_envelope(cursor.fetchone()[0])
        assert PiiBlindIndex.objects.filter(makerspace=space, object_id=row.pk).exists()
        reopen(operation, actor.pk)


def test_backfill_uses_bounded_pk_batches_and_resume_checkpoint(capsys):
    # Commands expose bounded batches and PK checkpoints, not WAL/disk/lag controls;
    # those production pause thresholds are deliberately external operator controls.
    space, user, first = _request("First")
    second = HardwareRequest.objects.create(
        makerspace=space, requester=user, requester_username="second", requester_name="Second",
        requester_contact_email="second@example.test",
    )
    with enabled_encryption():
        call_command(
            "backfill_scoped_pii", makerspace=space.pk,
            model="hardware_requests.HardwareRequest", batch_size=1,
            resume_after_pk=first.pk,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT id, requester_name FROM hardware_requests_hardwarerequest WHERE id = ANY(%s) ORDER BY id',
                [[first.pk, second.pk]],
            )
            values = dict(cursor.fetchall())
        assert not is_envelope(values[first.pk])
        assert is_envelope(values[second.pk])
        assert f"checkpoint={second.pk}" in capsys.readouterr().out
