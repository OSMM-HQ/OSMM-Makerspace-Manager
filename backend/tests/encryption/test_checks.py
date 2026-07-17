"""H1 wrapping-configuration system check (enabled-mode fail-closed startup)."""

from cryptography.fernet import Fernet
from django.test import override_settings

from apps.encryption.checks import check_pii_wrapping_configuration


def _ids(errors):
    return {e.id for e in errors}


def test_disabled_is_noop_and_touches_no_key():
    with override_settings(
        PII_ENCRYPTION_ENABLED=False,
        PII_KEY_BROKER="local",
        PII_MASTER_KEY="",
    ):
        assert check_pii_wrapping_configuration(None) == []


def test_enabled_local_missing_master_key_errors():
    with override_settings(
        PII_ENCRYPTION_ENABLED=True,
        PII_KEY_BROKER="local",
        PII_MASTER_KEY="",
    ):
        assert "encryption.E001" in _ids(check_pii_wrapping_configuration(None))


def test_enabled_local_malformed_master_key_errors():
    with override_settings(
        PII_ENCRYPTION_ENABLED=True,
        PII_KEY_BROKER="local",
        PII_MASTER_KEY="not-a-valid-fernet-key",
    ):
        assert "encryption.E001" in _ids(check_pii_wrapping_configuration(None))


def test_enabled_local_valid_master_key_passes():
    with override_settings(
        PII_ENCRYPTION_ENABLED=True,
        PII_KEY_BROKER="local",
        PII_MASTER_KEY=Fernet.generate_key().decode(),
    ):
        assert check_pii_wrapping_configuration(None) == []


def test_enabled_unknown_broker_errors():
    with override_settings(
        PII_ENCRYPTION_ENABLED=True,
        PII_KEY_BROKER="vault",
    ):
        assert "encryption.E004" in _ids(check_pii_wrapping_configuration(None))
