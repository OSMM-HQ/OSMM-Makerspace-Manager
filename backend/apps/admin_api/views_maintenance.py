from apps.admin_api.views_maintenance_documents import (
    MaintenanceLogDocumentDetailView,
    MaintenanceLogDocumentFinalizeView,
    MaintenanceLogDocumentPresignView,
    MaintenanceLogDocumentUrlView,
)
from apps.admin_api.views_maintenance_logs import MaintenanceLogListCreateView
from apps.admin_api.views_maintenance_schedules import (
    MaintenanceScheduleDeactivateView,
    MaintenanceScheduleDetailView,
    MaintenanceScheduleListCreateView,
)

__all__ = [
    "MaintenanceLogDocumentDetailView",
    "MaintenanceLogDocumentFinalizeView",
    "MaintenanceLogDocumentPresignView",
    "MaintenanceLogDocumentUrlView",
    "MaintenanceLogListCreateView",
    "MaintenanceScheduleDeactivateView",
    "MaintenanceScheduleDetailView",
    "MaintenanceScheduleListCreateView",
]

