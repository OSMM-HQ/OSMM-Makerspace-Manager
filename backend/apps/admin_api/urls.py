from django.urls import path

from apps.admin_api import api_client_views, views
from apps.admin_api.views_email_templates import (
    EmailTemplateDetailView,
    EmailTemplateListView,
    EmailTemplatePreviewView,
    EmailTemplateResetView,
)
from apps.admin_api.views_notification_recipients import NotificationRecipientsView
from apps.admin_api.views_platform import PlatformEmailSettingsView
from apps.makerspaces.models import MakerspaceMembership

urlpatterns = [
    path(
        "platform/email-settings",
        PlatformEmailSettingsView.as_view(),
        name="admin-platform-email-settings",
    ),
    path("makerspaces", views.MakerspaceListCreateView.as_view(), name="admin-makerspaces"),
    path("makerspaces/<int:pk>", views.MakerspaceDetailView.as_view(), name="admin-makerspace"),
    path(
        "makerspace/<int:makerspace_id>/return-policy",
        views.ReturnPolicyView.as_view(),
        name="admin-return-policy",
    ),
    path(
        "makerspace/<int:makerspace_id>/logo",
        views.MakerspaceLogoImageView.as_view(),
        name="admin-makerspace-logo",
    ),
    path(
        "makerspace/<int:makerspace_id>/cover",
        views.MakerspaceCoverImageView.as_view(),
        name="admin-makerspace-cover",
    ),
    path(
        "makerspace/<int:makerspace_id>/inventory",
        views.InventoryListCreateView.as_view(),
        name="admin-inventory",
    ),
    path("inventory/<int:pk>", views.InventoryDetailView.as_view(), name="admin-inventory-detail"),
    path(
        "inventory/<int:pk>/image",
        views.InventoryProductImageView.as_view(),
        name="admin-inventory-image",
    ),
    path(
        "inventory/needs-fix",
        views.NeedsFixShelfListView.as_view(),
        name="admin-needs-fix-shelf",
    ),
    path(
        "inventory/<int:pk>/needs-fix",
        views.NeedsFixActionView.as_view(),
        name="admin-needs-fix-action",
    ),
    path(
        "inventory/<int:pk>/lending-history",
        views.InventoryLendingHistoryView.as_view(),
        name="admin-inventory-lending-history",
    ),
    path(
        "inventory/<int:pk>/adjust-quantity",
        views.InventoryQuantityAdjustmentView.as_view(),
        name="admin-inventory-adjust-quantity",
    ),
    path(
        "makerspace/<int:makerspace_id>/categories",
        views.CategoryListCreateView.as_view(),
        name="admin-categories",
    ),
    path(
        "categories/<int:pk>",
        views.CategoryDetailView.as_view(),
        name="admin-category-detail",
    ),
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
        "makerspace/<int:makerspace_id>/notification-recipients",
        NotificationRecipientsView.as_view(),
        name="admin-notification-recipients",
    ),
    path(
        "makerspace/<int:makerspace_id>/email-templates",
        EmailTemplateListView.as_view(),
        name="admin-email-templates",
    ),
    path(
        "makerspace/<int:makerspace_id>/email-templates/preview",
        EmailTemplatePreviewView.as_view(),
        name="admin-email-template-preview",
    ),
    path(
        "makerspace/<int:makerspace_id>/email-templates/<str:stream>/<str:audience>/<str:key>/reset",
        EmailTemplateResetView.as_view(),
        name="admin-email-template-reset",
    ),
    path(
        "makerspace/<int:makerspace_id>/email-templates/<str:stream>/<str:audience>/<str:key>",
        EmailTemplateDetailView.as_view(),
        name="admin-email-template-detail",
    ),
    path(
        "api-clients/<int:pk>",
        api_client_views.ApiClientDetailView.as_view(),
        name="admin-api-client",
    ),
    path(
        "api-key-requests",
        api_client_views.ApiKeyRequestListCreateView.as_view(),
        name="admin-api-key-requests",
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
        "users/<int:pk>/reset-password",
        views.ResetUserPasswordView.as_view(),
        name="admin-user-reset-password",
    ),
    path(
        "users/<int:pk>/restore-access",
        views.RestoreUserAccessView.as_view(),
        name="user-restore-access",
    ),
    path("audit-logs", views.AuditLogListView.as_view(), name="admin-audit-logs"),
]
