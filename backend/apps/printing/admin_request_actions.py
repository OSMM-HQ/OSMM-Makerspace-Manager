from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.template.response import TemplateResponse
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.printing import workflow
from apps.printing.models import PrintRequest
from apps.printing.serializers import PrintStartSerializer


class PrintRequestWorkflowActions:
    @admin.action(description="Accept selected print requests")
    def accept_selected(self, request, queryset):
        success_count = 0
        for print_request in queryset:
            try:
                workflow.accept(print_request, request.user, price=0)
            except workflow.InvalidTransition as exc:
                self.message_user(request, f"{print_request.pk}: {exc}", level=messages.ERROR)
            else:
                success_count += 1

        if success_count:
            self.message_user(
                request,
                f"Accepted {success_count} print request(s).",
                level=messages.SUCCESS,
            )

    @admin.action(description="Reject selected print requests (with reason)")
    def reject_selected(self, request, queryset):
        if "apply" not in request.POST:
            return self._intermediate_action_response(
                request, queryset, "admin/printing/reject_action.html",
                "Reject selected print requests", "reject_selected",
            )

        reason = request.POST.get("reason", "").strip()
        if not reason:
            self.message_user(request, "Rejection reason is required.", level=messages.ERROR)
            return None

        success_count = 0
        for print_request in queryset:
            try:
                workflow.reject(print_request, request.user, reason)
            except workflow.InvalidTransition as exc:
                self.message_user(request, f"{print_request.pk}: {exc}", level=messages.ERROR)
            else:
                success_count += 1

        if success_count:
            self.message_user(
                request,
                f"Rejected {success_count} print request(s).",
                level=messages.SUCCESS,
            )
        return None

    @admin.action(description="Complete selected print requests")
    def complete_selected(self, request, queryset):
        success_count = 0
        for print_request in queryset:
            try:
                workflow.complete(print_request, request.user)
            except workflow.InvalidTransition as exc:
                self.message_user(request, f"{print_request.pk}: {exc}", level=messages.ERROR)
            else:
                success_count += 1

        if success_count:
            self.message_user(
                request,
                f"Completed {success_count} print request(s).",
                level=messages.SUCCESS,
            )

    @admin.action(description="Fail selected print requests (with reason)")
    def fail_selected(self, request, queryset):
        if "apply" not in request.POST:
            return self._intermediate_action_response(
                request, queryset, "admin/printing/fail_action.html",
                "Fail selected print requests", "fail_selected",
            )

        reason = request.POST.get("reason", "").strip()
        if not reason:
            self.message_user(request, "Failure reason is required.", level=messages.ERROR)
            return None
        try:
            percent_complete = int(request.POST.get("percent_complete", ""))
        except ValueError:
            self.message_user(request, "Percent complete is required.", level=messages.ERROR)
            return None
        if percent_complete < 0 or percent_complete > 100:
            self.message_user(request, "Percent complete must be from 0 to 100.", level=messages.ERROR)
            return None

        success_count = 0
        for print_request in queryset:
            try:
                workflow.fail(
                    print_request,
                    request.user,
                    reason,
                    percent_complete=percent_complete,
                )
            except workflow.InvalidTransition as exc:
                self.message_user(request, f"{print_request.pk}: {exc}", level=messages.ERROR)
            else:
                success_count += 1

        if success_count:
            self.message_user(
                request,
                f"Failed {success_count} print request(s).",
                level=messages.SUCCESS,
            )
        return None

    @admin.action(description="Start selected print requests (assign printer/spool)")
    def start_selected(self, request, queryset):
        if "apply" not in request.POST:
            return self._intermediate_action_response(
                request, queryset, "admin/printing/start_action.html",
                "Start selected print requests", "start_selected",
            )

        success_count = 0
        for print_request in queryset:
            raw = {
                "printer_id": request.POST.get(f"printer_id_{print_request.pk}", ""),
                "filament_spool_id": request.POST.get(f"filament_spool_id_{print_request.pk}", ""),
                "estimated_minutes": request.POST.get(f"estimated_minutes_{print_request.pk}", ""),
                "estimated_filament_grams": request.POST.get(
                    f"estimated_filament_grams_{print_request.pk}", ""
                ),
            }
            payload = {key: value for key, value in raw.items() if str(value).strip()}
            serializer = PrintStartSerializer(data=payload)
            if not serializer.is_valid():
                self.message_user(request, f"{print_request.pk}: {serializer.errors}", level=messages.ERROR)
                continue
            try:
                workflow.start(print_request, request.user, **serializer.validated_data)
            except (DRFValidationError, workflow.InvalidTransition) as exc:
                self.message_user(request, f"{print_request.pk}: {exc}", level=messages.ERROR)
            else:
                success_count += 1

        if success_count:
            self.message_user(
                request,
                f"Started {success_count} print request(s).",
                level=messages.SUCCESS,
            )
        return None

    @admin.action(description="Mark selected completed print requests as collected")
    def collect_selected(self, request, queryset):
        succeeded, skipped = 0, 0
        for print_request in queryset:
            if print_request.status != PrintRequest.Status.COMPLETED:
                skipped += 1
                continue
            try:
                workflow.mark_collected(print_request, request.user)
            except workflow.InvalidTransition as exc:
                skipped += 1
                self.message_user(request, f"{print_request.pk}: {exc}", level=messages.ERROR)
            else:
                succeeded += 1
        self._message_action_summary(request, "Collected", succeeded, skipped)

    @admin.action(description="Create reprints for selected failed print requests")
    def reprint_selected(self, request, queryset):
        succeeded, skipped = 0, 0
        for print_request in queryset:
            if print_request.status != PrintRequest.Status.FAILED:
                skipped += 1
                continue
            try:
                workflow.reprint(print_request, request.user)
            except workflow.InvalidTransition as exc:
                skipped += 1
                self.message_user(request, f"{print_request.pk}: {exc}", level=messages.ERROR)
            else:
                succeeded += 1
        self._message_action_summary(request, "Created reprints for", succeeded, skipped)

    def _message_action_summary(self, request, verb, succeeded, skipped):
        level = messages.SUCCESS if succeeded else messages.WARNING
        self.message_user(
            request,
            f"{verb} {succeeded} print request(s); skipped {skipped}.",
            level=level,
        )

    def _intermediate_action_response(
        self, request, queryset, template_name, title, action_name,
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
