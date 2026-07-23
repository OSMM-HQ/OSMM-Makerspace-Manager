from datetime import timedelta

import pytest
from django.utils import timezone

from apps.maintenance import services
from apps.maintenance.models import MaintenanceSchedule
from tests.maintenance.helpers import make_machine_setup


pytestmark = pytest.mark.django_db


def test_overdue_is_strict_active_scoped_and_ordered():
    _, manager, machine, _ = make_machine_setup("maintenance-overdue")
    today = timezone.localdate()
    oldest = MaintenanceSchedule.objects.create(
        machine=machine, description="Old", interval_days=1,
        next_due=today - timedelta(days=2), created_by=manager,
    )
    recent = MaintenanceSchedule.objects.create(
        machine=machine, description="Recent", interval_days=1,
        next_due=today - timedelta(days=1), created_by=manager,
    )
    MaintenanceSchedule.objects.create(
        machine=machine, description="Today", interval_days=1, next_due=today,
    )
    MaintenanceSchedule.objects.create(
        machine=machine, description="Inactive", interval_days=1,
        next_due=today - timedelta(days=3), is_active=False,
    )
    assert list(services.overdue_schedules(today=today)) == [oldest, recent]
    assert list(
        services.overdue_schedules(
            MaintenanceSchedule.objects.filter(pk=recent.pk), today=today,
        )
    ) == [recent]
