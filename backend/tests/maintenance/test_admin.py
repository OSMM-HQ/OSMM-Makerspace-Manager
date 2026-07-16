from django.test import RequestFactory

import pytest

from apps.maintenance.admin import (
    MaintenanceLogAdmin,
    MaintenanceLogDocumentAdmin,
    MaintenanceScheduleAdmin,
)
from apps.maintenance.models import (
    MaintenanceLog,
    MaintenanceLogDocument,
    MaintenanceSchedule,
)
from django.contrib.admin.sites import AdminSite


@pytest.mark.parametrize(
    ("admin_class", "model"),
    [
        (MaintenanceScheduleAdmin, MaintenanceSchedule),
        (MaintenanceLogAdmin, MaintenanceLog),
        (MaintenanceLogDocumentAdmin, MaintenanceLogDocument),
    ],
)
def test_control_plane_maintenance_models_are_view_only(admin_class, model):
    model_admin = admin_class(model, AdminSite())
    request = RequestFactory().get("/control/")
    assert model_admin.has_add_permission(request) is False
    assert model_admin.has_change_permission(request) is False
    assert model_admin.has_delete_permission(request) is False

