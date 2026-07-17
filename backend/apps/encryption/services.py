"""Atomic lifecycle operations for per-makerspace data-encryption keys."""

from dataclasses import dataclass
from threading import Lock

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.services import record
from apps.encryption.brokers.aws_kms import AwsKmsBroker
from apps.encryption.brokers.local import LocalMasterKeyBroker
from apps.encryption.cache import dek_cache, key_for
from apps.encryption.crypto import PiiKeyUnavailable, PiiUnavailable
from apps.encryption.models import MakerspaceEncryptionKey

_locks = {}
_locks_guard = Lock()


@dataclass(frozen=True)
class ActiveDek:
    key: MakerspaceEncryptionKey
    dek: bytes

    def __iter__(self):
        yield self.key
        yield self.dek


def _lock_for(makerspace_id):
    with _locks_guard:
        return _locks.setdefault(makerspace_id, Lock())


def _require_enabled():
    if not settings.PII_ENCRYPTION_ENABLED:
        raise PiiUnavailable()


def broker_for_backend(backend):
    if backend == MakerspaceEncryptionKey.BrokerBackend.LOCAL:
        return LocalMasterKeyBroker()
    if backend == MakerspaceEncryptionKey.BrokerBackend.AWS_KMS:
        return AwsKmsBroker()
    raise PiiUnavailable()


def configured_broker():
    return broker_for_backend(settings.PII_KEY_BROKER)


def _audit(action, makerspace, versions):
    record(
        None,
        action,
        makerspace=makerspace,
        meta={"makerspace_id": makerspace.id, "versions": list(versions)},
    )


def unwrap_dek(key_row):
    """Return an active/rotated row's DEK without caching failures or disabled rows."""
    _require_enabled()
    if key_row.status == MakerspaceEncryptionKey.Status.DISABLED:
        raise PiiKeyUnavailable()
    cache_key = key_for(key_row)
    cached = dek_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        dek = broker_for_backend(key_row.broker_backend).unwrap_dek(
            key_row.wrapped_dek, key_row.makerspace_id, key_row.version
        )
    except PiiUnavailable:
        raise
    except Exception as exc:
        raise PiiUnavailable() from exc
    dek_cache.set(cache_key, dek)
    return dek


def get_dek(makerspace_id, version):
    _require_enabled()
    try:
        key_row = MakerspaceEncryptionKey.objects.get(
            makerspace_id=makerspace_id, version=version
        )
    except MakerspaceEncryptionKey.DoesNotExist as exc:
        raise PiiKeyUnavailable() from exc
    return unwrap_dek(key_row)


def get_or_create_active_dek(makerspace_id):
    """Get or atomically create the active version for one makerspace."""
    _require_enabled()
    from apps.makerspaces.models import Makerspace

    with _lock_for(makerspace_id):
        with transaction.atomic():
            makerspace = Makerspace.objects.select_for_update().get(pk=makerspace_id)
            key_row = (
                MakerspaceEncryptionKey.objects.select_for_update()
                .filter(
                    makerspace=makerspace,
                    status=MakerspaceEncryptionKey.Status.ACTIVE,
                )
                .first()
            )
            if key_row is not None:
                return ActiveDek(key=key_row, dek=unwrap_dek(key_row))
            latest = (
                MakerspaceEncryptionKey.objects.select_for_update()
                .filter(makerspace=makerspace)
                .order_by("-version")
                .first()
            )
            version = 1 if latest is None else latest.version + 1
            broker = configured_broker()
            wrapped = broker.create_dek(makerspace.id, version)
            key_row = MakerspaceEncryptionKey.objects.create(
                makerspace=makerspace,
                version=version,
                wrapped_dek=wrapped.wrapped_dek,
                broker_backend=broker.backend,
                broker_key_id=wrapped.broker_key_id,
            )
            _audit("encryption.dek_created", makerspace, [key_row.version])
            dek_cache.set(key_for(key_row), wrapped.dek)
            return ActiveDek(key=key_row, dek=wrapped.dek)


def rotate_dek(makerspace_id):
    _require_enabled()
    from apps.makerspaces.models import Makerspace

    with _lock_for(makerspace_id), transaction.atomic():
        makerspace = Makerspace.objects.select_for_update().get(pk=makerspace_id)
        current = MakerspaceEncryptionKey.objects.select_for_update().get(
            makerspace=makerspace, status=MakerspaceEncryptionKey.Status.ACTIVE
        )
        next_version = current.version + 1
        broker = configured_broker()
        wrapped = broker.create_dek(makerspace.id, next_version)
        current.status = MakerspaceEncryptionKey.Status.ROTATED
        current.rotated_at = timezone.now()
        current.save(update_fields=["status", "rotated_at"])
        key_row = MakerspaceEncryptionKey.objects.create(
            makerspace=makerspace,
            version=next_version,
            wrapped_dek=wrapped.wrapped_dek,
            broker_backend=broker.backend,
            broker_key_id=wrapped.broker_key_id,
        )
        _audit("encryption.dek_rotated", makerspace, [current.version, key_row.version])
        dek_cache.invalidate(makerspace.id)
        dek_cache.set(key_for(key_row), wrapped.dek)
        return ActiveDek(key=key_row, dek=wrapped.dek)


def disable_dek(makerspace_id, version=None):
    _require_enabled()
    from apps.makerspaces.models import Makerspace

    with _lock_for(makerspace_id), transaction.atomic():
        makerspace = Makerspace.objects.select_for_update().get(pk=makerspace_id)
        filters = {"makerspace": makerspace}
        if version is None:
            filters["status"] = MakerspaceEncryptionKey.Status.ACTIVE
        else:
            filters["version"] = version
        key_row = MakerspaceEncryptionKey.objects.select_for_update().get(**filters)
        if key_row.status != MakerspaceEncryptionKey.Status.DISABLED:
            key_row.status = MakerspaceEncryptionKey.Status.DISABLED
            key_row.disabled_at = timezone.now()
            key_row.save(update_fields=["status", "disabled_at"])
            _audit("encryption.dek_disabled", makerspace, [key_row.version])
        dek_cache.invalidate(makerspace.id, key_row.version)
        return key_row


def rewrap_dek(makerspace_id, version):
    """Rewrap a local key from PII_MASTER_KEY_PREVIOUS to PII_MASTER_KEY."""
    _require_enabled()
    with _lock_for(makerspace_id), transaction.atomic():
        key_row = MakerspaceEncryptionKey.objects.select_for_update().get(
            makerspace_id=makerspace_id, version=version
        )
        if key_row.status == MakerspaceEncryptionKey.Status.DISABLED:
            raise PiiKeyUnavailable()
        if key_row.broker_backend != MakerspaceEncryptionKey.BrokerBackend.LOCAL:
            raise PiiUnavailable()
        broker = LocalMasterKeyBroker()
        try:
            dek = broker.unwrap_dek(
                key_row.wrapped_dek, makerspace_id, version, use_previous=True
            )
            replacement = broker.wrap_dek(dek, makerspace_id, version)
            key_row.wrapped_dek = replacement.wrapped_dek
            key_row.broker_key_id = replacement.broker_key_id
            key_row.save(update_fields=["wrapped_dek", "broker_key_id"])
        except PiiUnavailable:
            raise
        except Exception as exc:
            raise PiiUnavailable() from exc
        _audit("encryption.dek_rewrapped", key_row.makerspace, [version])
        dek_cache.invalidate(makerspace_id, version)
        return key_row
