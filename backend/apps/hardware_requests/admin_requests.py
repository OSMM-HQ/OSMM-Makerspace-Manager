from django import forms
from django.contrib import admin
from django.contrib import messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.template.response import TemplateResponse
from unfold.admin import ModelAdmin, TabularInline

from apps.hardware_requests.admin_workflow import WORKFLOW_EXCEPTIONS
from apps.hardware_requests.handover_workflow import (
    assign_box,
    set_return_due as workflow_set_return_due,
)
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem
from apps.hardware_requests.request_workflow import accept_request, reject_request
from config.admin_access import SuperuserOnlyModelAdmin


class ReturnDueForm(forms.Form):
    return_due_at = forms.DateTimeField(
        required=True,
        input_formats=[
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        ],
    )


class HardwareRequestItemInline(TabularInline):
    model = HardwareRequestItem
    extra = 0
    can_delete = False
    readonly_fields = (
        "product",
        "requested_quantity",
        "accepted_quantity",
        "issued_quantity",
        "returned_quantity",
        "damaged_quantity",
        "missing_quantity",
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(HardwareRequest)
class HardwareRequestAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    actions = [
        "accept_selected",
        "reject_selected",
        "assign_box_selected",
        "set_return_due",
    ]
    list_display = (
        "id",
        "status",
        "makerspace",
        "requester_username",
        "return_due_at",
        "created_at",
    )
    list_filter = ("status", "makerspace")
    search_fields = (
        "requester_username",
        "requested_for",
        "rejection_reason",
        "items__product__name",
    )
    readonly_fields = (
        "makerspace",
        "requester",
        "requester_username",
        "status",
        "requested_for",
        "rejection_reason",
        "accepted_by",
        "accepted_at",
        "assigned_box",
        "issued_by",
        "issued_at",
        "return_due_at",
        "return_reminder_sent_at",
        "closed_by",
        "closed_at",
        "public_token",
        "created_at",
        "updated_at",
    )
    fields = readonly_fields
    inlines = [HardwareRequestItemInline]

    # Requests are created by the public submit flow and mutated only through the
    # workflow services (the actions below). Direct add hits required readonly fields
    # and direct delete bypasses reservation/audit/notification cleanup.
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Accept selected requests")
    def accept_selected(self, request, queryset):
        success_count = 0
        for hardware_request in queryset:
            try:
                accept_request(request.user, hardware_request)
            except WORKFLOW_EXCEPTIONS as exc:
                self.message_user(
                    request,
                    f"{hardware_request.pk}: {exc}",
                    level=messages.ERROR,
                )
            else:
                success_count += 1

        if success_count:
            self.message_user(
                request,
                f"Accepted {success_count} hardware request(s).",
                level=messages.SUCCESS,
            )

    @admin.action(description="Reject selected requests (with reason)")
    def reject_selected(self, request, queryset):
        if "apply" not in request.POST:
            return self._intermediate_action_response(
                request,
                queryset,
                "admin/hardware_requests/reject_action.html",
                "Reject selected hardware requests",
                "reject_selected",
            )

        reason = request.POST.get("reason", "").strip()
        if not reason:
            self.message_user(
                request,
                "Rejection reason is required.",
                level=messages.ERROR,
            )
            return None

        success_count = 0
        for hardware_request in queryset:
            try:
                reject_request(request.user, hardware_request, reason)
            except WORKFLOW_EXCEPTIONS as exc:
                self.message_user(
                    request,
                    f"{hardware_request.pk}: {exc}",
                    level=messages.ERROR,
                )
            else:
                success_count += 1

        if success_count:
            self.message_user(
                request,
                f"Rejected {success_count} hardware request(s).",
                level=messages.SUCCESS,
            )
        return None

    @admin.action(description="Assign box to selected requests")
    def assign_box_selected(self, request, queryset):
        if "apply" not in request.POST:
            return self._intermediate_action_response(
                request,
                queryset,
                "admin/hardware_requests/assign_box_action.html",
                "Assign boxes to selected hardware requests",
                "assign_box_selected",
            )

        success_count = 0
        for hardware_request in queryset:
            box_code = request.POST.get(f"box_code_{hardware_request.pk}", "").strip()
            try:
                assign_box(request.user, hardware_request, box_code)
            except WORKFLOW_EXCEPTIONS as exc:
                self.message_user(
                    request,
                    f"{hardware_request.pk}: {exc}",
                    level=messages.ERROR,
                )
            else:
                success_count += 1

        if success_count:
            self.message_user(
                request,
                f"Assigned boxes for {success_count} hardware request(s).",
                level=messages.SUCCESS,
            )
        return None

    @admin.action(description="Set return due date for selected requests")
    def set_return_due(self, request, queryset):
        if "apply" not in request.POST:
            return self._intermediate_action_response(
                request,
                queryset,
                "admin/hardware_requests/set_return_due_action.html",
                "Set return due date for selected hardware requests",
                "set_return_due",
            )

        form = ReturnDueForm(request.POST)
        if not form.is_valid():
            self.message_user(request, form.errors, level=messages.ERROR)
            return None

        success_count = 0
        for hardware_request in queryset:
            try:
                workflow_set_return_due(
                    request.user,
                    hardware_request,
                    form.cleaned_data["return_due_at"],
                )
            except WORKFLOW_EXCEPTIONS as exc:
                self.message_user(
                    request,
                    f"{hardware_request.pk}: {exc}",
                    level=messages.ERROR,
                )
            else:
                success_count += 1

        if success_count:
            self.message_user(
                request,
                f"Updated return due date for {success_count} hardware request(s).",
                level=messages.SUCCESS,
            )
        return None

    def _intermediate_action_response(
        self,
        request,
        queryset,
        template_name,
        title,
        action_name,
    ):
        context = {
            **self.admin_site.each_context(request),
            "title": title,
            "queryset": queryset,
            "opts": self.model._meta,
            "action_name": action_name,
            "action_checkbox_name": ACTION_CHECKBOX_NAME,
        }
        return TemplateResponse(request, template_name, context)
