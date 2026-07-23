import pytest
from django.test import override_settings
from django.utils import timezone

from apps.integrations.models import NotificationPreference
from apps.maintenance import notifications, services, services_workflows
from apps.maintenance.models import MaintenanceLog
from tests.maintenance.helpers import make_machine_setup

pytestmark = pytest.mark.django_db


def test_each_maintenance_service_lifecycle_reaches_fanout_once(monkeypatch):
    calls = []
    monkeypatch.setattr(
        services_workflows,
        "notify_maintenance_lifecycle",
        lambda instance, name, **kwargs: calls.append((name, kwargs)),
    )
    _, manager, machine, _ = make_machine_setup("maintenance-fanout")
    services.log_maintenance(machine, actor=manager, summary="Cleaned")
    schedule = services.create_schedule(
        machine,
        actor=manager,
        description="Monthly",
        interval_days=30,
        next_due=timezone.localdate(),
    )
    services.update_schedule(schedule, actor=manager, description="Quarterly")
    services.complete_due(schedule, actor=manager, summary="Completed")
    services.deactivate_schedule(schedule, actor=manager)

    assert [name for name, _ in calls] == [
        "logged",
        "schedule_created",
        "schedule_updated",
        "schedule_completed",
        "schedule_deactivated",
    ]
    assert set(calls[3][1]) == {"log_id"}


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_maintenance_notifications_are_silent_until_email_cell_enabled(monkeypatch):
    makerspace, manager, machine, _ = make_machine_setup("maintenance-pref")
    log = MaintenanceLog.objects.create(
        machine=machine,
        performed_by=manager,
        summary="Checked belts",
        parts_note="No replacement needed",
    )
    monkeypatch.setattr(
        notifications,
        "staff_emails_for_feature",
        lambda *args, **kwargs: ["maintenance@example.com"],
    )
    silent = notifications.notify_maintenance_lifecycle(log, "logged", sync=True)
    assert silent.delivered_counts == {}

    NotificationPreference.objects.create(
        makerspace=makerspace,
        feature="maintenance",
        channel="email",
        enabled=True,
    )
    delivered = notifications.notify_maintenance_lifecycle(log, "logged", sync=True)
    assert delivered.delivered_counts == {"email": 1}
