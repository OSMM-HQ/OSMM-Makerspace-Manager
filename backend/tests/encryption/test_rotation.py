"""H4 key-rotation invariants: data ciphertext is independent of key wrapping."""

import uuid

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import override_settings

from apps.encryption.brokers.aws_kms import AwsKmsBroker
from apps.encryption.blind_index import active_generation, search_key_fingerprint
from apps.encryption.crypto import PiiUnavailable
from apps.encryption.models import MakerspaceEncryptionKey, PiiBlindIndex, SearchKeyGeneration
from apps.encryption.services import get_dek, rewrap_dek, rotate_dek
from apps.encryption.write_fence import close_global, reopen
from apps.hardware_requests.models import HardwareRequest
from apps.makerspaces.models import Makerspace
from tests.encryption.conftest import enabled_encryption

pytestmark = pytest.mark.django_db


def _request():
    token = uuid.uuid4().hex[:8]
    space = Makerspace.objects.create(name=f"Rotation {token}", slug=f"rotation-{token}")
    user = get_user_model().objects.create_user(username=f"rotation-{token}")
    row = HardwareRequest.objects.create(
        makerspace=space, requester=user, requester_username=user.username,
        requester_name="Ada Lovelace", requester_contact_email=f"{token}@example.test",
    )
    return space, row


def _raw_values(row):
    fields = ("requester_username", "requester_name", "requester_contact_email", "requester_contact_phone")
    columns = ", ".join(f'"{field}"' for field in fields)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {columns} FROM hardware_requests_hardwarerequest WHERE id = %s", [row.pk])
        return cursor.fetchone()


def _index_values(row):
    return list(PiiBlindIndex.objects.filter(object_id=row.pk).order_by("field_name").values_list(
        "field_name", "search_generation_id", "bloom_bits", "exact_hash"
    ))


def _version(envelope):
    return int(envelope.split(":")[3])


def test_dek_rotation_keeps_old_envelopes_readable_then_resave_moves_to_new_version():
    with enabled_encryption():
        space, row = _request()
        old_values, old_indexes = _raw_values(row), _index_values(row)
        assert {_version(value) for value in old_values if value} == {1}

        rotated = rotate_dek(space.pk)
        loaded = HardwareRequest.objects.get(pk=row.pk)
        assert loaded.requester_name == "Ada Lovelace"  # embedded version 1 still unwraps
        loaded.requester_name = loaded.requester_name
        loaded.requester_contact_email = loaded.requester_contact_email
        loaded.save()

        assert {_version(value) for value in _raw_values(loaded) if value} == {rotated.key.version}
        assert _index_values(loaded) == old_indexes  # DEK rotation does not require reindexing
        assert get_dek(space.pk, 1)  # retained version remains readable for backups


def test_local_and_mocked_kms_rewrap_change_only_key_wrapping_metadata():
    with enabled_encryption():
        space, row = _request()
        key = MakerspaceEncryptionKey.objects.get(makerspace=space, status="active")
        ciphertext, indexes, dek = _raw_values(row), _index_values(row), get_dek(space.pk, key.version)
        old_master = __import__("django.conf", fromlist=["settings"]).settings.PII_MASTER_KEY

        with override_settings(
            PII_MASTER_KEY=Fernet.generate_key().decode(), PII_MASTER_KEY_PREVIOUS=old_master,
        ):
            rewrapped = rewrap_dek(space.pk, key.version)
        assert bytes(rewrapped.wrapped_dek) != bytes(key.wrapped_dek)
        assert _raw_values(row) == ciphertext
        assert _index_values(row) == indexes

        class FakeKms:
            def encrypt(self, **kwargs):
                return {"CiphertextBlob": b"kms:" + kwargs["Plaintext"], "KeyId": "arn:test:new"}

        with override_settings(PII_AWS_KMS_KEY_ID="alias/pii-test"):
            broker = AwsKmsBroker()
            broker._client = lambda: FakeKms()
            wrapped = broker.wrap_dek(dek, space.pk, key.version)
        with transaction.atomic():
            current = MakerspaceEncryptionKey.objects.select_for_update().get(pk=key.pk)
            current.wrapped_dek = wrapped.wrapped_dek
            current.broker_backend = current.BrokerBackend.AWS_KMS
            current.broker_key_id = wrapped.broker_key_id
            current.save(update_fields=["wrapped_dek", "broker_backend", "broker_key_id"])
        assert _raw_values(row) == ciphertext
        assert _index_values(row) == indexes


def test_search_rotation_fence_rejects_old_fingerprint_until_complete_generation_is_active():
    """Exercise persisted generation states; fleet replacement itself is external."""
    actor = get_user_model().objects.create_user(
        username=f"rotation-operator-{uuid.uuid4().hex[:8]}", is_superuser=True, is_active=True,
    )
    with enabled_encryption():
        space, row = _request()
        old = SearchKeyGeneration.objects.get(status="active")
        operation = close_global("search_rotation", actor.pk, all_makerspaces=True)
        new_secret = Fernet.generate_key().decode()
        with override_settings(PII_SEARCH_HASH_KEY=new_secret):
            building = SearchKeyGeneration.objects.create(
                generation=old.generation + 1,
                key_fingerprint=search_key_fingerprint(), status="building",
            )
            with pytest.raises(PiiUnavailable):
                active_generation()
            # Partial/mixed artifacts are not activation-ready: the source index
            # still names N, while N+1 has no coverage at all.
            assert not PiiBlindIndex.objects.filter(object_id=row.pk, search_generation=building).exists()
            with transaction.atomic():
                old.status = "retired"
                old.save(update_fields=["status"])
                building.status = "active"
                building.save(update_fields=["status"])
            from django.core.management import call_command
            call_command(
                "reindex_scoped_pii", makerspace=space.pk,
                model="hardware_requests.HardwareRequest", batch_size=1,
            )
            assert PiiBlindIndex.objects.filter(object_id=row.pk, search_generation=building).count() == 2
            assert active_generation().pk == building.pk
        reopen(operation, actor.pk)
