"""Startup validation of the PII wrapping configuration (enabled mode only).

The full enabled-mode readiness contract (search-key fingerprint + DB-aware
all-DEK preflight + active search generation) is added in H3. H1 validates only
the key-broker / wrapping configuration so that enabling encryption with missing
or malformed key material fails ``manage.py check`` and process startup instead
of silently succeeding and failing at the first PII operation.

Disabled mode is completely key-independent: the check is a no-op and never
parses a key or imports boto3.
"""

from django.conf import settings
from django.core.checks import Error, register


@register()
def check_pii_wrapping_configuration(app_configs, **kwargs):
    if not settings.PII_ENCRYPTION_ENABLED:
        return []

    broker = settings.PII_KEY_BROKER
    errors = []
    if broker == "local":
        from apps.encryption.brokers.local import BinaryFernet

        try:
            BinaryFernet(settings.PII_MASTER_KEY)
        except Exception as exc:  # generic message only; no key material
            errors.append(
                Error(
                    "PII_ENCRYPTION_ENABLED is true but PII_MASTER_KEY is missing "
                    "or invalid for the local key broker.",
                    hint=str(exc),
                    id="encryption.E001",
                )
            )
    elif broker == "aws_kms":
        try:
            import boto3  # noqa: F401
        except ImportError:
            errors.append(
                Error(
                    "PII_KEY_BROKER=aws_kms requires boto3 "
                    "(install backend/requirements-kms.txt).",
                    id="encryption.E002",
                )
            )
        if not settings.PII_AWS_KMS_KEY_ID:
            errors.append(
                Error(
                    "PII_KEY_BROKER=aws_kms requires PII_AWS_KMS_KEY_ID.",
                    id="encryption.E003",
                )
            )
    else:
        errors.append(
            Error(
                "PII_KEY_BROKER must be 'local' or 'aws_kms', "
                f"got {broker!r}.",
                id="encryption.E004",
            )
        )
    from apps.encryption.blind_index import search_key
    try:
        key = search_key()
        if broker == "local":
            import base64
            master = base64.urlsafe_b64decode(settings.PII_MASTER_KEY.encode() + b"=" * (-len(settings.PII_MASTER_KEY) % 4))
            if key == master:
                errors.append(Error("PII_MASTER_KEY and PII_SEARCH_HASH_KEY must be independent.", id="encryption.E005"))
    except Exception:
        errors.append(Error("PII_ENCRYPTION_ENABLED is true but PII_SEARCH_HASH_KEY is missing or invalid.", id="encryption.E006"))
    return errors
