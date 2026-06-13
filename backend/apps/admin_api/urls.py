from django.urls import path

from apps.admin_api import api_client_views, views
from apps.makerspaces.models import MakerspaceMembership

urlpatterns = [
    path("makerspaces", views.MakerspaceListCreateView.as_view(), name="admin-makerspaces"),
    path("makerspaces/<int:pk>", views.MakerspaceDetailView.as_view(), name="admin-makerspace"),
    path(
        "makerspace/<int:makerspace_id>/return-policy",
        views.ReturnPolicyView.as_view(),
        name="admin-return-policy",
    ),
    path(
        "makerspace/<int:makerspace_id>/frontends",
        views.TenantFrontendListCreateView.as_view(),
        name="admin-tenant-frontends",
    ),
    path(
        "frontends/<int:pk>",
        views.TenantFrontendDetailView.as_view(),
        name="admin-tenant-frontend",
    ),
    path(
        "makerspace/<int:makerspace_id>/inventory",
        views.InventoryListCreateView.as_view(),
        name="admin-inventory",
    ),
    path("inventory/<int:pk>", views.InventoryDetailView.as_view(), name="admin-inventory-detail"),
    path(
        "makerspace/<int:makerspace_id>/inventory/import/preview",
        views.BulkImportPreviewView.as_view(),
        name="inventory-import-preview",
    ),
    path(
        "makerspace/<int:makerspace_id>/inventory/import/apply",
        views.BulkImportApplyView.as_view(),
        name="inventory-import-apply",
    ),
    path(
        "makerspace/<int:makerspace_id>/api-clients",
        api_client_views.ApiClientListCreateView.as_view(),
        name="admin-api-clients",
    ),
    path(
        "makerspace/<int:makerspace_id>/api-settings",
        api_client_views.ApiIntegrationSettingsView.as_view(),
        name="admin-api-settings",
    ),
    path(
        "api-clients/<int:pk>",
        api_client_views.ApiClientDetailView.as_view(),
        name="admin-api-client",
    ),
    path(
        "users/space-managers",
        views.StaffListCreateView.as_view(),
        {"role": MakerspaceMembership.Role.SPACE_MANAGER},
        name="admin-users-space-managers",
    ),
    path(
        "users/inventory-managers",
        views.StaffListCreateView.as_view(),
        {"role": MakerspaceMembership.Role.INVENTORY_MANAGER},
        name="admin-users-inventory-managers",
    ),
    path(
        "users/guest-admins",
        views.StaffListCreateView.as_view(),
        {"role": MakerspaceMembership.Role.GUEST_ADMIN},
        name="admin-users-guest-admins",
    ),
    path(
        "users/print-managers",
        views.StaffListCreateView.as_view(),
        {"role": MakerspaceMembership.Role.PRINT_MANAGER},
        name="admin-users-print-managers",
    ),
    path("users/<int:pk>/restrict", views.RestrictUserView.as_view(), name="user-restrict"),
    path(
        "users/<int:pk>/restore-access",
        views.RestoreUserAccessView.as_view(),
        name="user-restore-access",
    ),
    path("audit-logs", views.AuditLogListView.as_view(), name="admin-audit-logs"),
]
