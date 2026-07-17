import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings

from apps.hardware_requests.models import HardwareRequest
from apps.makerspaces.models import Makerspace


pytestmark = pytest.mark.django_db


def make_request():
    space = Makerspace.objects.create(name="Backfill Space", slug="backfill-space")
    user = get_user_model().objects.create_user(username="backfill-user")
    return space, HardwareRequest.objects.create(makerspace=space, requester=user, requester_username="backfill-user", requester_name="Backfill Name", requester_contact_email="backfill@example.test", requester_contact_phone="123")


def test_dry_run_is_key_free_and_mutation_requires_the_flag():
    space, row = make_request()
    call_command("backfill_scoped_pii", makerspace=space.pk, model="hardware_requests.HardwareRequest", dry_run=True)
    row.refresh_from_db()
    assert row.requester_name == "Backfill Name"
    with pytest.raises(Exception):
        call_command("backfill_scoped_pii", makerspace=space.pk, model="hardware_requests.HardwareRequest")


def test_backfill_encrypts_only_registered_fields():
    space, row = make_request()
    with override_settings(PII_ENCRYPTION_ENABLED=True, PII_ENCRYPTION_DUAL_READ=True, PII_MASTER_KEY=Fernet.generate_key().decode(), PII_KEY_BROKER="local"):
        call_command("backfill_scoped_pii", makerspace=space.pk, model="hardware_requests.HardwareRequest", batch_size=1)
        row.refresh_from_db()
        assert row.requester_name == "Backfill Name"
        assert row.requested_for == ""
