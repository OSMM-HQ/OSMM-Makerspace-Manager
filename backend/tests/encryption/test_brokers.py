import sys
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from apps.encryption.brokers.aws_kms import AwsKmsBroker
from apps.encryption.brokers.local import LocalMasterKeyBroker


def test_local_broker_is_binary_safe_and_independent_of_api_client_key(monkeypatch):
    key = Fernet.generate_key().decode()
    with override_settings(PII_MASTER_KEY=key, API_CLIENT_ENC_KEY=""):
        broker = LocalMasterKeyBroker()
        created = broker.create_dek(41, 1)
        assert len(created.dek) == 32
        assert created.dek not in created.wrapped_dek
        assert broker.unwrap_dek(created.wrapped_dek, 41, 1) == created.dek
        payload = b"\x00\xff\x80" + bytes(range(32))
        token = broker._fernet().encrypt(payload)
        assert broker._fernet().decrypt(token) == payload


@pytest.mark.parametrize("bad_key", ["", Fernet.generate_key().decode()])
def test_local_broker_rejects_bad_token_and_wrong_key_without_material(bad_key):
    first = Fernet.generate_key().decode()
    with override_settings(PII_MASTER_KEY=first):
        created = LocalMasterKeyBroker().create_dek(1, 1)
    with override_settings(PII_MASTER_KEY=bad_key):
        with pytest.raises(ImproperlyConfigured) as exc:
            LocalMasterKeyBroker().unwrap_dek(created.wrapped_dek + b"x", 1, 1)
    assert created.dek.hex() not in str(exc.value)


def test_local_broker_rejects_mismatched_payload_metadata():
    with override_settings(PII_MASTER_KEY=Fernet.generate_key().decode()):
        created = LocalMasterKeyBroker().create_dek(7, 1)
        with pytest.raises(ImproperlyConfigured):
            LocalMasterKeyBroker().unwrap_dek(created.wrapped_dek, 8, 1)


def test_kms_is_lazy_and_uses_context(monkeypatch):
    calls = []

    class Client:
        def generate_data_key(self, **kwargs):
            calls.append(kwargs)
            return {"Plaintext": b"a" * 32, "CiphertextBlob": b"wrapped", "KeyId": "arn"}

        def decrypt(self, **kwargs):
            calls.append(kwargs)
            return {"Plaintext": b"a" * 32}

    fake_boto = SimpleNamespace(client=lambda *args, **kwargs: Client())
    monkeypatch.setitem(sys.modules, "boto3", fake_boto)
    with override_settings(
        PII_AWS_KMS_KEY_ID="key-id", PII_AWS_KMS_REGION="ap-south-1"
    ):
        broker = AwsKmsBroker()
        created = broker.create_dek(5, 2)
        assert created.broker_key_id == "arn"
        assert broker.unwrap_dek(created.wrapped_dek, 5, 2) == b"a" * 32
    assert calls[0]["KeySpec"] == "AES_256"
    assert calls[0]["EncryptionContext"] == {
        "application": "inventory-manager-pii", "makerspace_id": "5", "dek_version": "2"
    }
