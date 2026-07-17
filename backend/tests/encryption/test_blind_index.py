"""H3 blind-index primitives, mapper index sync, and scoped search verification."""

import pytest
from contextlib import contextmanager

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.test import override_settings

from apps.encryption import blind_index as bi
from apps.encryption.crypto import PiiUnavailable
from apps.encryption.models import PiiBlindIndex, SearchKeyGeneration
from apps.encryption.search import indexed_candidates, legacy_plaintext_candidates, verified_ids
from apps.hardware_requests.models import HardwareRequest
from apps.makerspaces.models import Makerspace
from tests.encryption.conftest import enabled_encryption

pytestmark = pytest.mark.django_db

LABEL = "hardware_requests.HardwareRequest"


def _make(space, user, **overrides):
    data = dict(
        makerspace=space, requester=user, requester_username=user.username,
        requester_name="Ada Lovelace", requester_contact_email="ada@example.test",
        requester_contact_phone="+91 90000 11111", requested_for="scope",
    )
    data.update(overrides)
    return HardwareRequest.objects.create(**data)


# ---- primitives (pure, no DB) ------------------------------------------------

@contextmanager
def _search_key():
    with override_settings(PII_SEARCH_HASH_KEY=Fernet.generate_key().decode()):
        yield


def test_bloom_and_exact_sizes_and_name_determinism():
    with _search_key():
        kw = dict(generation=1, makerspace_id=7, model_label=LABEL, field_name="requester_name")
        bits = bi.bloom_bits("Ada Lovelace", **kw)
        assert len(bits) == 256
        assert bits == bi.bloom_bits("ada lovelace", **kw)  # NFKC+casefold normalization
        ekw = dict(generation=1, makerspace_id=7, model_label=LABEL, field_name="requester_contact_email")
        h = bi.exact_hash("Ada@Example.test", **ekw)
        assert len(h) == 32
        assert h == bi.exact_hash("ada@example.test", **ekw)  # canonical email


def test_scope_and_generation_domain_separation():
    with _search_key():
        base = dict(model_label=LABEL, field_name="requester_contact_email")
        a = bi.exact_hash("ada@example.test", generation=1, makerspace_id=7, **base)
        assert a != bi.exact_hash("ada@example.test", generation=2, makerspace_id=7, **base)  # generation
        assert a != bi.exact_hash("ada@example.test", generation=1, makerspace_id=8, **base)  # tenant
        assert a != bi.exact_hash("ada@example.test", generation=1, makerspace_id=7, model_label=LABEL, field_name="requester_name")


def test_short_value_has_empty_bloom():
    with _search_key():
        kw = dict(generation=1, makerspace_id=7, model_label=LABEL, field_name="requester_name")
        assert bi.bloom_bits("ab", **kw) == bytes(256)


# ---- generation binding / readiness -----------------------------------------

def test_active_generation_rejects_fingerprint_mismatch():
    from cryptography.fernet import Fernet
    from django.test import override_settings
    from django.utils import timezone

    with enabled_encryption():
        assert bi.active_generation().generation == 1
        # A different search key no longer matches the persisted fingerprint.
        with override_settings(PII_SEARCH_HASH_KEY=Fernet.generate_key().decode()):
            with pytest.raises(PiiUnavailable):
                bi.active_generation()


# ---- mapper index synchronization -------------------------------------------

def _index(row, field):
    return PiiBlindIndex.objects.filter(model_label=LABEL, object_id=row.pk, field_name=field).first()


def test_save_writes_generic_index_rows_for_name_and_email_only():
    space = Makerspace.objects.create(name="Idx", slug="idx")
    user = get_user_model().objects.create_user(username="idx-user")
    with enabled_encryption():
        row = _make(space, user)
        name_idx = _index(row, "requester_name")
        email_idx = _index(row, "requester_contact_email")
        assert name_idx is not None and name_idx.exact_hash is None  # bloom-only
        assert email_idx is not None and email_idx.exact_hash is not None  # bloom + exact
        assert _index(row, "requester_contact_phone") is None  # phone: no index
        assert _index(row, "requester_username") is None  # username snapshot: no index


def test_reindex_on_change_and_delete_on_blank():
    space = Makerspace.objects.create(name="Idx2", slug="idx2")
    user = get_user_model().objects.create_user(username="idx2-user")
    with enabled_encryption():
        row = _make(space, user)
        before = bytes(_index(row, "requester_name").bloom_bits)
        row.requester_name = "Grace Hopper"
        row.save()
        assert bytes(_index(row, "requester_name").bloom_bits) != before  # reindexed
        row.requester_name = ""
        row.save()
        assert _index(row, "requester_name") is None  # blank deletes the row


# ---- scoped search: candidate then decrypt-verify ---------------------------

def test_name_substring_search_verifies_and_drops_cross_tenant():
    space = Makerspace.objects.create(name="S1", slug="s1")
    other = Makerspace.objects.create(name="S2", slug="s2")
    u1 = get_user_model().objects.create_user(username="s1u")
    u2 = get_user_model().objects.create_user(username="s2u")
    with enabled_encryption():
        ada = _make(space, u1, requester_name="Ada Lovelace")
        _make(space, u1, requester_name="Bob Martin", requester_contact_email="bob@example.test")
        _make(other, u2, requester_name="Ada Lovelace", requester_contact_email="ada2@example.test")

        cand = indexed_candidates(makerspace_id=space.pk, model_label=LABEL, field_name="requester_name", term="lovelace")
        verified = verified_ids(HardwareRequest.objects.filter(pk__in=cand), field_name="requester_name", term="lovelace")
        assert verified == [ada.pk]  # tenant-scoped + verified; other makerspace's Ada excluded


def test_email_exact_search_matches_only_canonical_equal():
    space = Makerspace.objects.create(name="E1", slug="e1")
    user = get_user_model().objects.create_user(username="e1u")
    with enabled_encryption():
        target = _make(space, user, requester_contact_email="ada@example.test")
        _make(space, user, requester_contact_email="ada2@example.test")
        cand = indexed_candidates(makerspace_id=space.pk, model_label=LABEL, field_name="requester_contact_email", term="Ada@Example.test", exact=True)
        verified = verified_ids(HardwareRequest.objects.filter(pk__in=cand), field_name="requester_contact_email", term="ada@example.test", exact=True)
        assert verified == [target.pk]


def test_legacy_adapter_rejects_envelopes_and_matches_plaintext():
    space = Makerspace.objects.create(name="L1", slug="l1")
    user = get_user_model().objects.create_user(username="l1u")
    legacy = _make(space, user, requester_name="Legacy Plain")  # created flag-off => plaintext
    with enabled_encryption():
        encrypted = _make(space, user, requester_name="Legacy Plain")  # stored as envelope
        found = legacy_plaintext_candidates(
            HardwareRequest.objects.filter(makerspace=space), field_name="requester_name", term="legacy plain",
        )
        assert legacy.pk in found  # genuine plaintext matched
        assert encrypted.pk not in found  # envelope rejected before comparison
