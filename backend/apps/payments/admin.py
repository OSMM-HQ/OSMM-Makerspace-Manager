from django import forms
from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.payments.models import MakerspacePaymentSettings
from config.admin_access import SuperuserOnlyModelAdmin


class MakerspacePaymentSettingsAdminForm(forms.ModelForm):
    stripe_secret_key = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to retain the existing secret key.",
    )
    stripe_webhook_secret = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to retain the existing webhook secret.",
    )

    class Meta:
        model = MakerspacePaymentSettings
        fields = ("makerspace", "stripe_secret_key", "stripe_webhook_secret", "default_currency")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stored_secret_key = self.instance.stripe_secret_key
        self._stored_webhook_secret = self.instance.stripe_webhook_secret

    def save(self, commit=True):
        settings = super().save(commit=False)
        if self.cleaned_data["stripe_secret_key"]:
            settings.set_stripe_secret_key(self.cleaned_data["stripe_secret_key"])
        else:
            settings.stripe_secret_key = self._stored_secret_key
        if self.cleaned_data["stripe_webhook_secret"]:
            settings.set_stripe_webhook_secret(self.cleaned_data["stripe_webhook_secret"])
        else:
            settings.stripe_webhook_secret = self._stored_webhook_secret
        if commit:
            settings.save()
        return settings


@admin.register(MakerspacePaymentSettings)
class MakerspacePaymentSettingsAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    form = MakerspacePaymentSettingsAdminForm
    list_display = ("makerspace", "configured", "default_currency")
    list_filter = ("makerspace",)
    search_fields = ("makerspace__name", "makerspace__slug", "makerspace__public_code")

    @admin.display(boolean=True, description="Configured")
    def configured(self, obj):
        return obj.is_configured
