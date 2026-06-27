from django.urls import path

from apps.admin_api import api_client_views, views
from apps.admin_api.views_email_templates import (
    EmailTemplateDetailView,
    EmailTemplateListView,
    EmailTemplatePreviewView,
    EmailTemplateResetView,
)
from apps.admin_api.views_email_logs import EmailLogListView, EmailLogRetryView
from apps.admin_api.views_notification_recipients import NotificationRecipientsView
from apps.admin_api.views_notification_rules import NotificationRulesView
from apps.admin_api.views_platform import PlatformEmailSettingsView
from apps.admin_api.views_warranty import (
    AssetWarrantyView,
    MakerspaceWarrantyReportView,
    PrinterWarrantyView,
)
from apps.admin_api.views_warranty_documents import (
    WarrantyDocumentCreateView,
    WarrantyDocumentDeleteView,
    WarrantyDocumentPresignView,
    WarrantyDocumentUrlView,
)
from apps.makerspaces.models import MakerspaceMembership
from apps.printing.views_printer_image import PrinterImageView

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
    path(
        "makerspace/<int:makerspace_id>/inventory/export",
        views.InventoryExportView.as_view(),
        name="admin-inventory-export",
    ),
    path("inventory/<int:pk>", views.InventoryDetailView.as_view(), name="admin-inventory-detail"),
    path("inventory/<int:pk>/qr-history", views.ProductQrHistoryView.as_view(), name="admin-inventory-qr-history"),
    path("inventory/<int:product_pk>/assets", views.InventoryAssetListView.as_view(), name="admin-inventory-assets"),
    path("assets/<int:pk>/fix-status", views.InventoryAssetStatusActionView.as_view(), name="admin-inventory-asset-fix-status"),
    path("assets/<int:pk>/warranty", AssetWarrantyView.as_view(), name="admin-asset-warranty"),
    path("assets/<int:pk>/qr-history", views.AssetQrHistoryView.as_view(), name="admin-inventory-asset-qr-history"),
    path(
        "inventory/<int:pk>/image",
        views.InventoryProductImageView.as_view(),
        name="admin-inventory-image",
    ),
    path(
        "printing/printers/<int:pk>/image",
        PrinterImageView.as_view(),
        name="admin-printer-image",
    ),
    path(
        "printing/printers/<int:pk>/warranty",
        PrinterWarrantyView.as_view(),
        name="admin-printer-warranty",
    ),
    path(
        "warranty/<int:pk>/documents/presign",
        WarrantyDocumentPresignView.as_view(),
        name="admin-warranty-document-presign",
    ),
    path(
        "warranty/<int:pk>/documents",
        WarrantyDocumentCreateView.as_view(),
        name="admin-warranty-documents",
    ),
    path(
        "warranty/documents/<int:pk>/url",
        WarrantyDocumentUrlView.as_view(),
        name="admin-warranty-document-url",
    ),
    path(
        "warranty/documents/<int:pk>",
        WarrantyDocumentDeleteView.as_view(),
        name="admin-warranty-document-detail",
    ),
    path(
        "makerspace/<int:makerspace_id>/warranties",
        MakerspaceWarrantyReportView.as_view(),
        name="admin-makerspace-warranties",
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
        "makerspace/<int:makerspace_id>/inventory/import/jobs",
        views.BulkImportJobListCreateView.as_view(),
        name="inventory-import-jobs",
    ),
    path(
        "makerspace/<int:makerspace_id>/inventory/import/jobs/<int:job_id>",
        views.BulkImportJobDetailView.as_view(),
        name="inventory-import-job-detail",
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
        "makerspace/<int:makerspace_id>/notification-rules",
        NotificationRulesView.as_view(),
        name="admin-notification-rules",
    ),
    path(
        "makerspace/<int:makerspace_id>/email-templates",
        EmailTemplateListView.as_view(),
        name="admin-email-templates",
    ),
    path(
        "makerspace/<int:makerspace_id>/email-logs",
        EmailLogListView.as_view(),
        name="admin-email-logs",
    ),
    path(
        "makerspace/<int:makerspace_id>/email-logs/<int:pk>/retry",
        EmailLogRetryView.as_view(),
        name="admin-email-log-retry",
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
        "api-clients/<int:pk>/rotate-secret",
        api_client_views.ApiClientRotateSecretView.as_view(),
        name="admin-api-client-rotate-secret",
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
