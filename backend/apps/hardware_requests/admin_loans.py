from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.hardware_requests.asset_link_models import HardwareRequestItemAsset
from apps.hardware_requests.return_models import RequesterAccountability, ReturnEvent
from apps.hardware_requests.self_checkout_models import (
    PublicProblemReport,
    PublicToolLoan,
)
from config.admin_access import SuperuserOnlyModelAdmin
from apps.encryption.admin_search import ScopedPiiAdminSearchMixin


@admin.register(PublicToolLoan)
class PublicToolLoanAdmin(ScopedPiiAdminSearchMixin, SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = (
        "id",
        "makerspace",
        "status",
        "request",
        "requester",
        "target_label",
        "source",
        "checked_out_at",
    )
    pii_search_model = "hardware_requests.HardwareRequest"
    pii_search_relation = "request__"
    pii_search_fields = ("requester_name", "requester_contact_email")
    list_filter = ("makerspace", "status", "source")
    search_fields = (
        "requester__username",
        "requester__email",
        "target_label",
    )
    readonly_fields = (
        "makerspace",
        "qr_code",
        "request",
        "requester",
        "target_type",
        "target_id",
        "target_label",
        "asset_ids",
        "qr_ids",
        "status",
        "source",
        "checked_out_at",
        "due_at",
        "returned_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(PublicProblemReport)
class PublicProblemReportAdmin(ScopedPiiAdminSearchMixin, SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = (
        "id",
        "makerspace",
        "loan",
        "requester",
        "created_at",
        "resolved_at",
        "resolved_by",
    )
    pii_search_model = "hardware_requests.HardwareRequest"
    pii_search_relation = "request__"
    pii_search_fields = ("requester_name", "requester_contact_email")
    list_filter = ("makerspace", "resolved_at", "created_at")
    search_fields = (
        "requester__username",
        "requester__email",
        "note",
    )
    readonly_fields = (
        "makerspace",
        "loan",
        "request",
        "requester",
        "note",
        "created_at",
    )
    fields = (
        "makerspace",
        "loan",
        "request",
        "requester",
        "note",
        "created_at",
        "resolved_at",
        "resolved_by",
    )

    def has_add_permission(self, request):
        return False

@admin.register(ReturnEvent)
class ReturnEventAdmin(ScopedPiiAdminSearchMixin, SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("id", "makerspace", "request", "box", "actor", "created_at")
    list_filter = ("makerspace", "created_at")
    search_fields = (
        "request__requester__username",
        "request__requester__email",
        "actor__username",
        "actor__email",
        "box__label",
        "box__code",
    )
    pii_search_model = "hardware_requests.HardwareRequest"
    pii_search_relation = "request__"
    pii_search_fields = ("requester_name", "requester_contact_email")
    readonly_fields = (
        "request",
        "makerspace",
        "box",
        "evidence",
        "remark",
        "actor",
        "created_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RequesterAccountability)
class RequesterAccountabilityAdmin(ScopedPiiAdminSearchMixin, SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = (
        "id",
        "makerspace",
        "requester",
        "request",
        "issue_type",
        "quantity",
        "created_at",
    )
    pii_search_model = "hardware_requests.HardwareRequest"
    pii_search_relation = "request__"
    pii_search_fields = ("requester_name", "requester_contact_email")
    list_filter = ("makerspace", "issue_type", "created_at")
    search_fields = (
        "requester__username",
        "requester__email",
        "request_item__product__name",
        "description",
    )
    readonly_fields = (
        "requester",
        "request",
        "request_item",
        "makerspace",
        "issue_type",
        "description",
        "evidence_photo",
        "quantity",
        "created_by",
        "created_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(HardwareRequestItemAsset)
class HardwareRequestItemAssetAdmin(ScopedPiiAdminSearchMixin, SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = (
        "id",
        "request_item",
        "asset",
        "asset_makerspace",
        "outcome",
        "issued_at",
        "returned_at",
    )
    pii_search_model = "hardware_requests.HardwareRequest"
    pii_search_relation = "request_item__request__"
    pii_search_fields = ("requester_name", "requester_contact_email")
    list_filter = ("asset__makerspace", "outcome")
    search_fields = (
        "request_item__request__requester__username",
        "request_item__product__name",
        "asset__asset_tag",
        "asset__serial_number",
    )
    readonly_fields = (
        "request_item",
        "asset",
        "outcome",
        "issued_at",
        "returned_at",
        "return_event",
    )
    fields = readonly_fields

    @admin.display(description="Makerspace", ordering="asset__makerspace")
    def asset_makerspace(self, obj):
        return obj.asset.makerspace if obj.asset_id else "-"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
