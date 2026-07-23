"""Local Fernet KEK broker with a binary-safe payload format."""

import base64
import hashlib
import secrets
import struct

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.encryption.brokers.base import KeyBroker, WrappedDek, require_dek


class BinaryFernet:
    """Small bytes-only Fernet wrapper; DEK payloads are never text decoded."""

    def __init__(self, encoded_key: str | bytes):
        if isinstance(encoded_key, str):
            encoded_key = encoded_key.encode("ascii")
        try:
            decoded = base64.urlsafe_b64decode(encoded_key)
        except Exception as exc:
            raise ImproperlyConfigured("PII master key is not configured correctly.") from exc
        if len(decoded) != 32:
            raise ImproperlyConfigured("PII master key is not configured correctly.")
        try:
            self._fernet = Fernet(encoded_key)
        except (TypeError, ValueError) as exc:
            raise ImproperlyConfigured("PII master key is not configured correctly.") from exc

    def encrypt(self, value: bytes) -> bytes:
        if not isinstance(value, bytes):
            raise TypeError("BinaryFernet accepts bytes only.")
        return self._fernet.encrypt(value)

    def decrypt(self, token: bytes) -> bytes:
        if not isinstance(token, bytes):
            raise ImproperlyConfigured("PII wrapped key is invalid.")
        try:
            return self._fernet.decrypt(token)
        except InvalidToken as exc:
            raise ImproperlyConfigured("PII wrapped key is unavailable.") from exc


class LocalMasterKeyBroker(KeyBroker):
    backend = "local"

    def __init__(self, master_key=None, previous_master_key=None):
        self._master_key = master_key
        self._previous_master_key = previous_master_key

    def _key(self, *, previous=False):
        configured = self._previous_master_key if previous else self._master_key
        if configured is None:
            configured = (
                settings.PII_MASTER_KEY_PREVIOUS
                if previous
                else settings.PII_MASTER_KEY
            )
        if not configured:
            raise ImproperlyConfigured("PII master key is not configured correctly.")
        return configured

    def _fernet(self, *, previous=False) -> BinaryFernet:
        return BinaryFernet(self._key(previous=previous))

    @property
    def broker_key_id(self) -> str:
        key = self._key()
        if isinstance(key, str):
            key = key.encode("ascii")
        try:
            raw = base64.urlsafe_b64decode(key)
        except Exception as exc:
            raise ImproperlyConfigured("PII master key is not configured correctly.") from exc
        if len(raw) != 32:
            raise ImproperlyConfigured("PII master key is not configured correctly.")
        return "sha256:" + hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _payload(makerspace_id: int, version: int, dek: bytes) -> bytes:
        if makerspace_id < 0 or version < 1:
            raise ImproperlyConfigured("PII key metadata is invalid.")
        return struct.pack(">QQ", makerspace_id, version) + require_dek(dek)

    def create_dek(self, makerspace_id: int, version: int) -> WrappedDek:
        return self.wrap_dek(secrets.token_bytes(32), makerspace_id, version)

    def wrap_dek(self, dek: bytes, makerspace_id: int, version: int) -> WrappedDek:
        """Wrap an existing 32-byte DEK for a KEK rewrap operation."""
        dek = require_dek(dek)
        return WrappedDek(
            dek=dek,
            wrapped_dek=self._fernet().encrypt(self._payload(makerspace_id, version, dek)),
            broker_key_id=self.broker_key_id,
        )

    def unwrap_dek(self, wrapped_dek, makerspace_id, version, *, use_previous=False):
        payload = self._fernet(previous=use_previous).decrypt(bytes(wrapped_dek))
        if len(payload) != 48:
            raise ImproperlyConfigured("PII wrapped key is unavailable.")
        stored_makerspace, stored_version = struct.unpack(">QQ", payload[:16])
        if stored_makerspace != makerspace_id or stored_version != version:
            raise ImproperlyConfigured("PII wrapped key is unavailable.")
        return require_dek(payload[16:])
