from django import forms
from unfold.widgets import (
    UnfoldAdminEmailInputWidget,
    UnfoldAdminIntegerFieldWidget,
    UnfoldAdminPasswordWidget,
    UnfoldAdminTextInputWidget,
    UnfoldBooleanSwitchWidget,
)

from apps.apiclients.models import ApiClient
from apps.integrations.smtp_validation import validate_smtp_settings


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
    smtp_use_tls = forms.BooleanField(required=False, widget=UnfoldBooleanSwitchWidget)
    smtp_use_ssl = forms.BooleanField(required=False, widget=UnfoldBooleanSwitchWidget)
    smtp_from_email = forms.EmailField(required=False, widget=UnfoldAdminEmailInputWidget)

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
                "smtp_use_ssl",
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

    def clean(self):
        cleaned = super().clean()
        validate_smtp_settings(cleaned, getattr(self.instance, "makerspace", None))
        return cleaned
