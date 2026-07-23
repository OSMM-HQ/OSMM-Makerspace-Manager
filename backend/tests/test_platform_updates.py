from io import StringIO

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.updates import services
from apps.updates.models import PlatformUpdateSettings
from tests.return_helpers import authenticated_client, make_user

pytestmark = pytest.mark.django_db


def superadmin(name="updates-superadmin"):
    return make_user(
        name,
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )


def test_update_settings_are_superadmin_only_and_toggle_is_audited():
    regular = make_user("updates-regular", access_status=User.AccessStatus.ACTIVE)
    root = superadmin()
    url = reverse("admin-platform-update-settings")

    assert authenticated_client(regular).get(url).status_code == 403

    client = authenticated_client(root)
    response = client.patch(
        url,
        {"automatic_updates_enabled": True, "status": "running"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["automatic_updates_enabled"] is True
    assert response.data["status"] == PlatformUpdateSettings.Status.IDLE
    event = AuditLog.objects.get(action="platform.update_settings_updated")
    assert event.actor == root
    assert event.meta == {"automatic_updates_enabled": True}


def test_update_now_queues_audited_request():
    root = superadmin("updates-queue-superadmin")
    response = authenticated_client(root).post(
        reverse("admin-platform-update-now"),
        format="json",
    )

    assert response.status_code == 202
    assert response.data["status"] == PlatformUpdateSettings.Status.QUEUED
    assert response.data["update_requested_at"] is not None
    assert AuditLog.objects.filter(
        actor=root,
        action="platform.update_requested",
    ).exists()


def test_automatic_updates_can_be_turned_off():
    settings = PlatformUpdateSettings.load()
    settings.automatic_updates_enabled = True
    settings.save(update_fields=("automatic_updates_enabled", "updated_at"))
    root = superadmin("updates-off-superadmin")

    response = authenticated_client(root).patch(
        reverse("admin-platform-update-settings"),
        {"automatic_updates_enabled": False},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["automatic_updates_enabled"] is False
    assert services.claim_update(
        current_version="0.5.0-main.1.aaaaaaaaaaaa",
        available_version="0.5.0-main.2.bbbbbbbbbbbb",
    ) is False
    event = AuditLog.objects.get(action="platform.update_settings_updated")
    assert event.meta == {"automatic_updates_enabled": False}


def test_host_claim_respects_toggle_and_manual_queue():
    settings = PlatformUpdateSettings.load()

    assert services.claim_update(
        current_version="0.5.0-main.1.aaaaaaaaaaaa",
        available_version="0.5.0-main.2.bbbbbbbbbbbb",
    ) is False

    services.queue_update()
    assert services.claim_update(
        current_version="0.5.0-main.1.aaaaaaaaaaaa",
        available_version="0.5.0-main.2.bbbbbbbbbbbb",
    ) is True
    settings.refresh_from_db()
    assert settings.status == PlatformUpdateSettings.Status.RUNNING
    assert settings.target_version == "0.5.0-main.2.bbbbbbbbbbbb"
    assert settings.update_requested_at is None


def test_backup_and_completion_status_are_safe_for_display():
    services.record_backup("../../pre-update-20260723T100000Z.sql.gz")
    services.complete_update("0.5.0-main.2.bbbbbbbbbbbb")
    settings = PlatformUpdateSettings.load()

    assert settings.last_backup_name == "pre-update-20260723T100000Z.sql.gz"
    assert settings.last_backup_at is not None
    assert settings.status == PlatformUpdateSettings.Status.IDLE
    assert settings.current_version == "0.5.0-main.2.bbbbbbbbbbbb"
    assert settings.last_updated_at is not None


def test_update_control_command_enables_and_claims_updates():
    output = StringIO()
    call_command("update_control", "set-auto", "on", stdout=output)
    call_command(
        "update_control",
        "claim",
        "--current=0.5.0-main.1.aaaaaaaaaaaa",
        "--available=0.5.0-main.2.bbbbbbbbbbbb",
        "--force",
        stdout=output,
    )

    settings = PlatformUpdateSettings.load()
    assert settings.automatic_updates_enabled is True
    assert settings.status == PlatformUpdateSettings.Status.RUNNING
    assert output.getvalue().splitlines() == ["on", "run"]
