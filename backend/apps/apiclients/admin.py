import secrets

from django import forms
from django.contrib import admin, messages
from unfold.admin import ModelAdmin
from unfold.widgets import (
    UnfoldAdminEmailInputWidget,
    UnfoldAdminIntegerFieldWidget,
    UnfoldAdminPasswordWidget,
    UnfoldAdminTextInputWidget,
    UnfoldBooleanSwitchWidget,
)

from apps.accounts import rbac
from apps.accounts.models import User
from apps.apiclients.models import ApiClient
from apps.apiclients.services import sync_makerspace_origins
from apps.makerspaces.models import Makerspace

MANAGER_ROLES = (User.Role.SUPERADMIN, User.Role.SPACE_MANAGER)


def _is_superadmin(user):
    return user.is_superuser or user.role == User.Role.SUPERADMIN


class ApiClientAdminForm(forms.ModelForm):
    telegram_group_chat_id = forms.CharField(
        required=False, widget=UnfoldAdminTextInputWidget
    )
    telegram_bot_token = forms.CharField(
        required=False, widget=UnfoldAdminPasswordWidget(render_value=False)
    )
    smtp_host = forms.CharField(required=False, widget=UnfoldAdminTextInputWidget)
    smtp_port = forms.IntegerField(
        required=False, min_value=1, widget=UnfoldAdminIntegerFieldWidget
    )
    smtp_username = forms.CharField(required=False, widget=UnfoldAdminTextInputWidget)
    smtp_password = forms.CharField(
        required=False, widget=UnfoldAdminPasswordWidget(render_value=False)
    )
    smtp_use_tls = forms.BooleanField(
        required=False, widget=UnfoldBooleanSwitchWidget
    )
    smtp_from_email = forms.EmailField(
        required=False, widget=UnfoldAdminEmailInputWidget
    )

    class Meta:
        model = ApiClient
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        makerspace = getattr(self.instance, "makerspace", None)
        if makerspace:
            for field in (
                "telegram_group_chat_id",
                "smtp_host",
                "smtp_port",
                "smtp_username",
                "smtp_use_tls",
                "smtp_from_email",
            ):
                self.fields[field].initial = getattr(makerspace, field)
            self.fields["telegram_bot_token"].help_text = (
                "Token is already set. Leave blank to keep it."
                if makerspace.telegram_bot_token
                else "Enter bot token."
            )
            self.fields["smtp_password"].help_text = (
                "SMTP password is already set. Leave blank to keep it."
                if makerspace.smtp_password
                else "Enter SMTP password."
            )


@admin.register(ApiClient)
class ApiClientAdmin(ModelAdmin):
    form = ApiClientAdminForm
    list_display = (
        "label",
        "client_id",
        "makerspace",
        "makerspace_public_code",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "makerspace")
    readonly_fields = (
        "client_id",
        "makerspace_public_code",
        "makerspace_public_api_key",
        "created_by",
        "created_at",
        "updated_at",
    )
    fields = (
        "label",
        "makerspace",
        "allowed_origins",
        "is_active",
        "telegram_group_chat_id",
        "telegram_bot_token",
        "smtp_host",
        "smtp_port",
        "smtp_username",
        "smtp_password",
        "smtp_use_tls",
        "smtp_from_email",
        "client_id",
        "makerspace_public_code",
        "makerspace_public_api_key",
        "created_by",
        "created_at",
        "updated_at",
    )

    # Only ACTIVE superadmin + makerspace admins reach this admin at all
    # (review fixes #1 correct signatures, #2 access_status).
    def has_module_permission(self, request):
        u = getattr(request, "user", None)
        return bool(
            u and u.is_authenticated and u.is_active
            and u.access_status == User.AccessStatus.ACTIVE
            and (u.is_superuser or u.role in MANAGER_ROLES)
        )

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)

    # Admins see/edit only clients in their assigned makerspaces (superadmin: all).
    def get_queryset(self, request):
        return rbac.scope_by_makerspace(
            request.user, super().get_queryset(request), "makerspace_id"
        )

    # Admins can only target their own makerspaces and MUST pick one (no global client).
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "makerspace" and not _is_superadmin(request.user):
            scope = rbac.resolve_scope(request.user)
            ids = [] if scope is rbac.ALL else scope
            kwargs["queryset"] = Makerspace.objects.filter(id__in=ids)
            kwargs["required"] = True
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    # Generate + reveal the secret once at creation.
    def save_model(self, request, obj, form, change):
        new_secret = None
        if not change:
            obj.created_by = request.user
            new_secret = secrets.token_urlsafe(32)
            obj.set_secret(new_secret)
        super().save_model(request, obj, form, change)
        self._save_makerspace_settings(obj, form)
        sync_makerspace_origins(obj.makerspace)
        if new_secret:
            messages.warning(
                request,
                f"Client secret for {obj.client_id} (shown once - copy it now): {new_secret}",
            )

    def delete_model(self, request, obj):
        makerspace = obj.makerspace
        super().delete_model(request, obj)
        sync_makerspace_origins(makerspace)

    def delete_queryset(self, request, queryset):
        makerspaces = list({client.makerspace for client in queryset.select_related("makerspace")})
        super().delete_queryset(request, queryset)
        for makerspace in makerspaces:
            sync_makerspace_origins(makerspace)

    def _save_makerspace_settings(self, obj, form):
        if not obj.makerspace_id:
            return
        makerspace = obj.makerspace
        text_fields = [
            "telegram_group_chat_id",
            "smtp_host",
            "smtp_username",
            "smtp_from_email",
        ]
        for field in text_fields:
            setattr(makerspace, field, form.cleaned_data.get(field) or "")
        if form.cleaned_data.get("telegram_bot_token"):
            makerspace.set_telegram_bot_token(form.cleaned_data["telegram_bot_token"])
        if form.cleaned_data.get("smtp_password"):
            makerspace.set_smtp_password(form.cleaned_data["smtp_password"])
        makerspace.smtp_port = form.cleaned_data.get("smtp_port") or 587
        makerspace.smtp_use_tls = bool(form.cleaned_data.get("smtp_use_tls"))
        makerspace.save(
            update_fields=[
                *text_fields,
                "telegram_bot_token",
                "smtp_password",
                "smtp_port",
                "smtp_use_tls",
                "updated_at",
            ]
        )

    @admin.display(description="Makerspace code")
    def makerspace_public_code(self, obj):
        return obj.makerspace.public_code if obj.makerspace_id else "-"

    @admin.display(description="Legacy public API key")
    def makerspace_public_api_key(self, obj):
        return obj.makerspace.public_api_key if obj.makerspace_id else "-"
