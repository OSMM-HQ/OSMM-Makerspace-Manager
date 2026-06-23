import pytest

from apps.integrations.notification_rules import (
    is_requester_muted,
    muted_targets,
    role_muted,
)
from apps.makerspaces.models import MakerspaceMembership
from tests.test_issue import make_space

pytestmark = pytest.mark.django_db
Role = MakerspaceMembership.Role


def fail_filter(*args, **kwargs):
    raise RuntimeError("mute store unavailable")


def test_role_mute_lookup_fails_closed_for_mutable_lifecycle_event(monkeypatch):
    makerspace = make_space("mute-fail-closed-role")
    monkeypatch.setattr(
        "apps.integrations.notification_rules.EmailNotificationMute.objects.filter",
        fail_filter,
    )

    assert role_muted(makerspace, "hardware", "accepted", Role.INVENTORY_MANAGER) is True


def test_requester_mute_lookup_does_not_suppress_always_on_event(monkeypatch):
    makerspace = make_space("mute-fail-open-return-reminder")
    monkeypatch.setattr(
        "apps.integrations.notification_rules.EmailNotificationMute.objects.filter",
        fail_filter,
    )

    assert is_requester_muted(makerspace, "hardware", "return_reminder") is False


def test_muted_targets_lookup_fails_closed_for_mutable_targets(monkeypatch):
    makerspace = make_space("mute-fail-closed-targets")
    monkeypatch.setattr(
        "apps.integrations.notification_rules.EmailNotificationMute.objects.filter",
        fail_filter,
    )

    assert muted_targets(makerspace, "printing", "accepted") == {
        "requester",
        Role.SPACE_MANAGER.value,
        Role.PRINT_MANAGER.value,
    }


def test_muted_targets_lookup_does_not_suppress_nonmutable_event(monkeypatch):
    makerspace = make_space("mute-fail-open-targets")
    monkeypatch.setattr(
        "apps.integrations.notification_rules.EmailNotificationMute.objects.filter",
        fail_filter,
    )

    assert muted_targets(makerspace, "hardware", "return_reminder") == set()
