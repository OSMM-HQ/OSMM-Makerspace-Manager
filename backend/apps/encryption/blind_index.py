"""The intentionally small, domain-separated blind-index primitive set."""

import base64
import hashlib
import hmac
import unicodedata

from django.conf import settings

from apps.encryption.crypto import PiiUnavailable
from apps.encryption.models import PiiBlindIndex, SearchKeyGeneration

_FINGERPRINT_PREFIX = b"inventory-manager:pii-search-key-fingerprint:v1\0"
_BITS = 2048


def search_key() -> bytes:
    """Decode exactly the independent 256-bit HMAC key, without exposing it."""
    try:
        value = settings.PII_SEARCH_HASH_KEY.encode("ascii")
        key = base64.urlsafe_b64decode(value + b"=" * (-len(value) % 4))
    except Exception as exc:
        raise PiiUnavailable() from exc
    if len(key) != 32:
        raise PiiUnavailable()
    return key


def search_key_fingerprint(key=None) -> bytes:
    return hashlib.sha256(_FINGERPRINT_PREFIX + (search_key() if key is None else key)).digest()


def normalized_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value or "").casefold().strip().split())


def canonical_email(value: str) -> str:
    # EventRegistration's historical contract is trim/lower; NFKC is retained for
    # generic fields so matching semantics are coherent with names.
    return unicodedata.normalize("NFKC", value or "").strip().lower()


def active_generation() -> SearchKeyGeneration:
    try:
        generation = SearchKeyGeneration.objects.get(status=SearchKeyGeneration.Status.ACTIVE)
    except (SearchKeyGeneration.DoesNotExist, SearchKeyGeneration.MultipleObjectsReturned) as exc:
        raise PiiUnavailable() from exc
    if not hmac.compare_digest(bytes(generation.key_fingerprint), search_key_fingerprint()):
        raise PiiUnavailable()
    return generation


def _mac(purpose: str, generation: int, makerspace_id: int, model_label: str, field_name: str, value: str) -> bytes:
    payload = f"{purpose}:g{generation}:{makerspace_id}:{model_label}:{field_name}:{value}".encode("utf-8")
    return hmac.new(search_key(), payload, hashlib.sha256).digest()


def bloom_bits(value: str, *, generation: int, makerspace_id: int, model_label: str, field_name: str) -> bytes:
    normalized = normalized_name(value)
    result = bytearray(256)
    if len(normalized) < 3:
        return bytes(result)
    for offset in range(len(normalized) - 2):
        digest = _mac("bloom:v1", generation, makerspace_id, model_label, field_name, normalized[offset:offset + 3])
        for part in range(6):
            position = int.from_bytes(digest[part * 2:part * 2 + 2], "big") % _BITS
            result[position // 8] |= 1 << (position % 8)
    return bytes(result)


def exact_hash(value: str, *, generation: int, makerspace_id: int, model_label: str, field_name: str) -> bytes:
    return _mac("exact:v1", generation, makerspace_id, model_label, field_name, canonical_email(value))


def event_email_hash(value: str, *, generation: int, makerspace_id: int, event_id: int) -> bytes:
    payload = f"event-email:v1:g{generation}:{makerspace_id}:{event_id}:{canonical_email(value)}".encode("utf-8")
    return hmac.new(search_key(), payload, hashlib.sha256).digest()


def upsert_index(instance, field, plaintext, generation=None):
    """Write only registry-approved generic rows, after source encryption succeeded."""
    if field.index_kind not in {"bloom", "bloom_exact"}:
        return
    generation = generation or active_generation()
    makerspace_id = field and __import__("apps.encryption.registry", fromlist=["makerspace_id_for"]).makerspace_id_for(instance, field)
    lookup = {"makerspace_id": makerspace_id, "model_label": field.model_label, "object_id": instance.pk, "field_name": field.field_name}
    if not plaintext:
        PiiBlindIndex.objects.filter(**lookup).delete()
        return
    defaults = {
        "search_generation": generation,
        "bloom_bits": bloom_bits(plaintext, generation=generation.generation, makerspace_id=makerspace_id, model_label=field.model_label, field_name=field.field_name),
        "exact_hash": exact_hash(plaintext, generation=generation.generation, makerspace_id=makerspace_id, model_label=field.model_label, field_name=field.field_name) if field.index_kind == "bloom_exact" else None,
        "algorithm_version": 1,
    }
    PiiBlindIndex.objects.update_or_create(**lookup, defaults=defaults)


def sync_event_hash(instance, plaintext, generation=None):
    generation = generation or active_generation()
    if not plaintext:
        instance.email_exact_hash = None
        instance.email_hash_generation = None
        return
    instance.email_exact_hash = event_email_hash(plaintext, generation=generation.generation, makerspace_id=instance.event.makerspace_id, event_id=instance.event_id)
    instance.email_hash_generation = generation
