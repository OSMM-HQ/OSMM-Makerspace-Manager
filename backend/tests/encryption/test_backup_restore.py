"""Restore prerequisites and immutable key-row retention checks."""

import uuid

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import connection, transaction

from apps.encryption.cache import dek_cache
from apps.encryption.crypto import PiiUnavailable
from apps.encryption.models import MakerspaceEncryptionKey, SearchKeyGeneration
from apps.encryption.readiness import assert_ready
from apps.encryption.services import rotate_dek
from apps.hardware_requests.models import HardwareRequest
from apps.makerspaces.models import Makerspace
from tests.encryption.conftest import enabled_encryption

pytestmark = pytest.mark.django_db


def _encrypted_request():
    token = uuid.uuid4().hex[:8]
    space = Makerspace.objects.create(name=f"Restore {token}", slug=f"restore-{token}")
    user = get_user_model().objects.create_user(username=f"restore-{token}")
    return space, HardwareRequest.objects.create(
        makerspace=space, requester=user, requester_username=user.username,
        requester_name="Restore Me", requester_contact_email=f"{token}@example.test",
    )


def test_restored_old_key_version_stays_readable_and_missing_authority_fails_closed():
    with enabled_encryption():
        space, row = _encrypted_request()
        rotate_dek(space.pk)
        restored = HardwareRequest.objects.get(pk=row.pk)
        assert restored.requester_name == "Restore Me"  # row is a version-1 restore fixture
        assert_ready()

        key = MakerspaceEncryptionKey.objects.get(makerspace=space, version=1)
        key.wrapped_dek = b"unreadable-backup-row"
        key.save(update_fields=["wrapped_dek"])
        dek_cache.clear()
        with pytest.raises(PiiUnavailable):
            assert_ready()

    # Search material is also a restore prerequisite, even before source rows are read.
    with enabled_encryption():
        from apps.encryption.models import PiiBlindIndex
        PiiBlindIndex.objects.all().delete()
        SearchKeyGeneration.objects.all().delete()
        with pytest.raises(PiiUnavailable):
            assert_ready()


def test_every_key_row_delete_path_is_blocked_including_database_trigger():
    with enabled_encryption():
        space, _ = _encrypted_request()
        key = MakerspaceEncryptionKey.objects.get(makerspace=space)
        with pytest.raises(RuntimeError):
            key.delete()
        with pytest.raises(RuntimeError):
            MakerspaceEncryptionKey.objects.filter(pk=key.pk).delete()
        assert MakerspaceEncryptionKey not in admin.site._registry
        with pytest.raises(Exception), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("DELETE FROM encryption_makerspaceencryptionkey WHERE id = %s", [key.pk])
        assert MakerspaceEncryptionKey.objects.filter(pk=key.pk).exists()
