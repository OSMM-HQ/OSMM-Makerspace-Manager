"""Shared helpers for the scoped-PII encryption test suite."""

from contextlib import contextmanager

from cryptography.fernet import Fernet
from django.test import override_settings
from django.utils import timezone


@contextmanager
def enabled_encryption(dual_read=True):
    """Enable encryption with independent master/search keys and a bound generation.

    Mirrors the real enabled-mode contract: an active SearchKeyGeneration whose
    fingerprint matches the configured PII_SEARCH_HASH_KEY must exist before any
    indexed mapped write. Requires DB access.
    """
    with override_settings(
        PII_ENCRYPTION_ENABLED=True,
        PII_ENCRYPTION_DUAL_READ=dual_read,
        PII_MASTER_KEY=Fernet.generate_key().decode(),
        PII_KEY_BROKER="local",
        PII_SEARCH_HASH_KEY=Fernet.generate_key().decode(),
    ):
        from apps.encryption.blind_index import search_key_fingerprint
        from apps.encryption.models import SearchKeyGeneration

        SearchKeyGeneration.objects.get_or_create(
            generation=1,
            defaults={
                "key_fingerprint": search_key_fingerprint(),
                "status": SearchKeyGeneration.Status.ACTIVE,
                "activated_at": timezone.now(),
            },
        )
        yield
