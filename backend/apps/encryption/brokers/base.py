"""Interfaces shared by DEK wrapping backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured


def require_dek(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) != 32:
        raise ImproperlyConfigured("PII key material is not configured correctly.")
    return value


@dataclass(frozen=True)
class WrappedDek:
    dek: bytes
    wrapped_dek: bytes
    broker_key_id: str

    def __post_init__(self):
        require_dek(self.dek)


class KeyBroker(ABC):
    """Wraps and unwraps 32-byte data-encryption keys without logging them."""

    backend: str

    @abstractmethod
    def create_dek(self, makerspace_id: int, version: int) -> WrappedDek:
        """Create a new 32-byte DEK and return its opaque wrapped representation."""

    @abstractmethod
    def wrap_dek(self, dek: bytes, makerspace_id: int, version: int) -> WrappedDek:
        """Wrap exactly the supplied 32-byte DEK for the given key metadata."""

    @abstractmethod
    def unwrap_dek(
        self,
        wrapped_dek: bytes,
        makerspace_id: int,
        version: int,
        *,
        use_previous: bool = False,
    ) -> bytes:
        """Return the matching 32-byte DEK or raise a non-secret configuration error."""
