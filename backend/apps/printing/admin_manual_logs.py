from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from rest_framework.exceptions import ValidationError as DRFValidationError
from unfold.admin import ModelAdmin

from apps.accounts import rbac
from apps.makerspaces.guards import require_module
from apps.makerspaces.models import Makerspace
from apps.printing import services_manual_logs
from apps.printing.models import FilamentSpool, ManualPrintLog, PrintPrinter
from apps.printing.workflow import InvalidTransition
from config.admin_access import SuperuserOnlyModelAdmin


def _visible_makerspaces():
    qs = Makerspace.objects.filter(archived_at__isnull=True)
    hidden = rbac.superadmin_hidden_makerspace_ids()
    return qs.exclude(id__in=hidden) if hidden else qs


class ManualPrintLogAdminForm(forms.Form):
    makerspace = forms.ModelChoiceField(queryset=Makerspace.objects.none())
    printer = forms.ModelChoiceField(queryset=PrintPrinter.objects.none())
    filament_spool = forms.ModelChoiceField(queryset=FilamentSpool.objects.none())
    grams_used = forms.DecimalField(max_digits=8, decimal_places=2, min_value=0)
    duration_minutes = forms.IntegerField(min_value=0, required=False, initial=0)
    outcome = forms.ChoiceField(
        choices=ManualPrintLog.Outcome.choices,
        required=False,
        initial=ManualPrintLog.Outcome.SUCCESS,
    )
    percent_complete = forms.IntegerField(
        min_value=0, max_value=100, required=False, initial=100
    )
    reason = forms.CharField(required=False, widget=forms.Textarea)
    title = forms.CharField(max_length=200)
    requester_name = forms.CharField(max_length=120, required=False)
    contact_email = forms.EmailField(required=False)
    contact_phone = forms.CharField(max_length=40, required=False)
    note = forms.CharField(required=False, widget=forms.Textarea)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        visible = _visible_makerspaces()
        self.fields["makerspace"].queryset = visible
        makerspace_id = self.data.get("makerspace") or self.initial.get("makerspace")
        # Only populate dependent choices once the id is confirmed visible, so a
        # manually-posted hidden/archived makerspace id can't surface its printer/
        # spool names in the rebound (invalid) form.
        if makerspace_id and visible.filter(id=makerspace_id).exists():
            self.fields["printer"].queryset = PrintPrinter.objects.filter(
                makerspace_id=makerspace_id,
                is_active=True,
            )
            self.fields["filament_spool"].queryset = FilamentSpool.objects.filter(
                makerspace_id=makerspace_id,
                is_active=True,
            )

    def clean_grams_used(self):
        grams = self.cleaned_data["grams_used"]
        if grams <= 0:
            raise forms.ValidationError("Must be greater than 0.")
        return grams


@admin.register(ManualPrintLog)
class ManualPrintLogAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("title", "outcome", "requester_name", "contact_email", "contact_phone", "makerspace", "printer", "filament_spool", "grams_used", "created_at")
    list_filter = ("makerspace", "printer", "outcome")
    search_fields = ("title", "requester_name", "contact_email", "contact_phone", "note", "printer__name", "filament_spool__material")
    readonly_fields = (
        "makerspace",
        "printer",
        "filament_spool",
        "grams_used",
        "duration_minutes",
        "outcome",
        "percent_complete",
        "reason",
        "title",
        "requester_name",
        "contact_email",
        "contact_phone",
        "note",
        "logged_by",
        "created_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return self._has_superuser_access(request)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def add_view(self, request, form_url="", extra_context=None):
        form = ManualPrintLogAdminForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            data = form.cleaned_data
            try:
                # Match the API path (assert_can_manage_makerspace) — reject a
                # makerspace whose printing module is disabled before mutating spools.
                require_module(data["makerspace"], "printing")
                log = services_manual_logs.log_manual_print(
                    request.user,
                    data["makerspace"],
                    data["printer"],
                    data["filament_spool"],
                    data["grams_used"],
                    data["title"],
                    data.get("note", ""),
                    duration_minutes=data.get("duration_minutes") or 0,
                    requester_name=data.get("requester_name", ""),
                    contact_email=data.get("contact_email", ""),
                    contact_phone=data.get("contact_phone", ""),
                    outcome=data.get("outcome") or ManualPrintLog.Outcome.SUCCESS,
                    percent_complete=(
                        data.get("percent_complete")
                        if data.get("percent_complete") is not None
                        else 100
                    ),
                    reason=data.get("reason", ""),
                )
            except (InvalidTransition, DRFValidationError) as exc:
                form.add_error(None, str(exc))
            else:
                self.message_user(request, "Manual print log created.", level=messages.SUCCESS)
                return redirect(
                    reverse("admin:printing_manualprintlog_change", args=[log.pk])
                )

        context = {
            **self.admin_site.each_context(request),
            "title": "Add manual print log",
            "opts": self.model._meta,
            "form": form,
        }
        context.update(extra_context or {})
        return TemplateResponse(request, "admin/printing/manual_print_log_add.html", context)
