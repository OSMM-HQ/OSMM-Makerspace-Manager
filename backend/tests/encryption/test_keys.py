import pytest
from cryptography.fernet import Fernet
from django.contrib import admin
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import override_settings
from unittest.mock import patch

from apps.audit.models import AuditLog
from apps.encryption.cache import dek_cache
from apps.encryption.crypto import PiiKeyUnavailable
from apps.encryption.models import MakerspaceEncryptionKey
from apps.encryption.services import (
    disable_dek,
    get_or_create_active_dek,
    get_dek,
    rewrap_dek,
    rotate_dek,
)
from apps.makerspaces.models import Makerspace


@pytest.fixture
def makerspace(db):
    return Makerspace.objects.create(name="Encrypted Space", slug="encrypted-space")


@pytest.fixture
def encryption_settings():
    with override_settings(
        PII_ENCRYPTION_ENABLED=True,
        PII_KEY_BROKER="local",
        PII_MASTER_KEY=Fernet.generate_key().decode(),
        PII_MASTER_KEY_PREVIOUS="",
        PII_DEK_CACHE_TTL_SECONDS=300,
    ):
        dek_cache.clear()
        yield
        dek_cache.clear()


def test_first_use_creates_one_active_key_and_audits(makerspace, encryption_settings):
    first = get_or_create_active_dek(makerspace.id)
    again = get_or_create_active_dek(makerspace.id)
    assert first.key.id == again.key.id
    assert MakerspaceEncryptionKey.objects.filter(makerspace=makerspace, status="active").count() == 1
    assert AuditLog.objects.filter(action="encryption.dek_created", makerspace=makerspace).count() == 1


def test_disabled_mode_does_not_need_or_create_key_rows(makerspace):
    with override_settings(PII_ENCRYPTION_ENABLED=False, PII_MASTER_KEY=""):
        assert Makerspace.objects.get(pk=makerspace.pk).name == "Encrypted Space"
        with pytest.raises(Exception):
            get_or_create_active_dek(makerspace.id)
    assert not MakerspaceEncryptionKey.objects.filter(makerspace=makerspace).exists()


def test_rotation_preserves_old_version_and_disable_fails_closed(makerspace, encryption_settings):
    first = get_or_create_active_dek(makerspace.id)
    second = rotate_dek(makerspace.id)
    assert second.key.version == 2
    assert get_dek(makerspace.id, first.key.version) == first.dek
    disable_dek(makerspace.id, first.key.version)
    with pytest.raises(PiiKeyUnavailable):
        get_dek(makerspace.id, first.key.version)
    assert AuditLog.objects.filter(action="encryption.dek_rotated").exists()
    assert AuditLog.objects.filter(action="encryption.dek_disabled").exists()


def test_cache_ttl_zero_and_rewrap_invalidate_entries(makerspace, encryption_settings):
    active = get_or_create_active_dek(makerspace.id)
    dek_cache.clear()
    with patch("apps.encryption.services.broker_for_backend", wraps=__import__(
        "apps.encryption.services", fromlist=["broker_for_backend"]
    ).broker_for_backend) as broker_for_backend:
        assert get_dek(makerspace.id, active.key.version) == active.dek
        assert get_dek(makerspace.id, active.key.version) == active.dek
        assert broker_for_backend.call_count == 1
    with override_settings(PII_DEK_CACHE_TTL_SECONDS=0):
        dek_cache.clear()
        with patch("apps.encryption.services.broker_for_backend", wraps=__import__(
            "apps.encryption.services", fromlist=["broker_for_backend"]
        ).broker_for_backend) as broker_for_backend:
            get_dek(makerspace.id, active.key.version)
            get_dek(makerspace.id, active.key.version)
            assert broker_for_backend.call_count == 2

    new_master = Fernet.generate_key().decode()
    old_master = __import__("django.conf", fromlist=["settings"]).settings.PII_MASTER_KEY
    with override_settings(PII_MASTER_KEY=new_master, PII_MASTER_KEY_PREVIOUS=old_master):
        rewrap_dek(makerspace.id, active.key.version)
        assert get_dek(makerspace.id, active.key.version) == active.dek
    assert AuditLog.objects.filter(action="encryption.dek_rewrapped").exists()


def test_constraints_and_every_delete_path_are_blocked(makerspace, encryption_settings):
    key = get_or_create_active_dek(makerspace.id).key
    with pytest.raises(IntegrityError), transaction.atomic():
        MakerspaceEncryptionKey.objects.create(
            makerspace=makerspace, version=1, wrapped_dek=b"x", broker_backend="local", broker_key_id="x"
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        MakerspaceEncryptionKey.objects.create(
            makerspace=makerspace, version=2, wrapped_dek=b"x", broker_backend="local", broker_key_id="x"
        )
    with pytest.raises(RuntimeError):
        key.delete()
    with pytest.raises(RuntimeError):
        MakerspaceEncryptionKey.objects.filter(pk=key.pk).delete()
    assert MakerspaceEncryptionKey not in admin.site._registry
    with pytest.raises(ProtectedError):
        makerspace.delete()
    with connection.cursor() as cursor, pytest.raises(Exception):
        cursor.execute("DELETE FROM encryption_makerspaceencryptionkey WHERE id = %s", [key.id])
