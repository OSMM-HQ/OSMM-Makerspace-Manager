"""Bounded in-process cache for successfully unwrapped active DEKs."""

from dataclasses import dataclass
from threading import RLock
from time import monotonic

from django.conf import settings


@dataclass(frozen=True)
class CacheKey:
    makerspace_id: int
    version: int
    broker_backend: str
    broker_key_id: str


class DekCache:
    def __init__(self):
        self._entries = {}
        self._lock = RLock()

    @staticmethod
    def _ttl():
        return max(0, settings.PII_DEK_CACHE_TTL_SECONDS)

    def get(self, key):
        if not self._ttl():
            return None
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, dek = entry
            if monotonic() >= expires_at:
                self._entries.pop(key, None)
                return None
            return dek

    def set(self, key, dek):
        ttl = self._ttl()
        if not ttl:
            return
        with self._lock:
            self._entries[key] = (monotonic() + ttl, dek)

    def invalidate(self, makerspace_id, version=None):
        with self._lock:
            for key in tuple(self._entries):
                if key.makerspace_id == makerspace_id and (
                    version is None or key.version == version
                ):
                    self._entries.pop(key, None)

    def clear(self):
        with self._lock:
            self._entries.clear()


dek_cache = DekCache()


def key_for(key_row):
    return CacheKey(
        makerspace_id=key_row.makerspace_id,
        version=key_row.version,
        broker_backend=key_row.broker_backend,
        broker_key_id=key_row.broker_key_id,
    )
