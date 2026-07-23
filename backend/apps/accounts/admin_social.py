from django import forms
from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.accounts.models_social import PlatformSocialAuthSettings, SocialIdentity
from config.admin_access import SuperuserOnlyModelAdmin


class PlatformSocialAuthSettingsForm(forms.ModelForm):
    apple_private_key_raw = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Write-only. Leave blank to keep the current encrypted Apple key.",
    )

    class Meta:
        model = PlatformSocialAuthSettings
        exclude = ("apple_private_key",)

    def save(self, commit=True):
        row = super().save(commit=False)
        if self.cleaned_data.get("apple_private_key_raw"):
            row.set_apple_private_key(self.cleaned_data["apple_private_key_raw"])
        if commit:
            row.save()
            from apps.accounts.social_csp import clear_social_csp_cache

            clear_social_csp_cache()
        return row


@admin.register(PlatformSocialAuthSettings)
class PlatformSocialAuthSettingsAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    form = PlatformSocialAuthSettingsForm

    def has_add_permission(self, request):
        return not PlatformSocialAuthSettings.objects.exists()


@admin.register(SocialIdentity)
class SocialIdentityAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("id", "user", "provider", "created_at")
    readonly_fields = ("user", "provider", "provider_sub", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
