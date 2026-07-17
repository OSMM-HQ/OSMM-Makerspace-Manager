"""H3 reindex verification gate + search-key binding actor/audit (review fixes)."""

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.audit.models import AuditLog
from apps.encryption.models import PiiBlindIndex, SearchKeyGeneration
from apps.hardware_requests.models import HardwareRequest
from apps.makerspaces.models import Makerspace
from tests.encryption.conftest import enabled_encryption

pytestmark = pytest.mark.django_db


def _request(space, user, **overrides):
    data = dict(
        makerspace=space, requester=user, requester_username=user.username,
        requester_name="Verify Me", requester_contact_email="v@example.test",
        requester_contact_phone="1", requested_for="x",
    )
    data.update(overrides)
    return HardwareRequest.objects.create(**data)


def test_verify_only_flags_missing_index():
    space = Makerspace.objects.create(name="V", slug="v-idx")
    user = get_user_model().objects.create_user(username="v-user")
    with enabled_encryption():
        row = _request(space, user)
        PiiBlindIndex.objects.filter(object_id=row.pk, field_name="requester_name").delete()
        with pytest.raises(CommandError):
            call_command("reindex_scoped_pii", makerspace=space.pk, model="hardware_requests.HardwareRequest", verify_only=True)


def test_verify_only_passes_when_indexes_present():
    space = Makerspace.objects.create(name="V2", slug="v2-idx")
    user = get_user_model().objects.create_user(username="v2-user")
    with enabled_encryption():
        _request(space, user, requester_name="All Good", requester_contact_email="g@example.test")
        call_command("reindex_scoped_pii", makerspace=space.pk, model="hardware_requests.HardwareRequest", verify_only=True)


def test_bind_requires_active_superuser():
    plain = get_user_model().objects.create_user(username="plain")
    with enabled_encryption():
        SearchKeyGeneration.objects.all().delete()
        with pytest.raises(CommandError):
            call_command("bind_pii_search_key", initial=True, actor_id=plain.pk)


def test_bind_creates_generation_and_audits():
    actor = get_user_model().objects.create_user(username="pii-super", is_superuser=True, is_staff=True)
    with enabled_encryption():
        SearchKeyGeneration.objects.all().delete()
        call_command("bind_pii_search_key", initial=True, actor_id=actor.pk)
        assert SearchKeyGeneration.objects.filter(generation=1, status="active").exists()
        assert AuditLog.objects.filter(action="encryption.search_key_bound").exists()
