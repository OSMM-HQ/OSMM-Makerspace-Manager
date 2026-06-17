from django.db import transaction
from rest_framework import serializers

from apps.accounts.models import User
from apps.integrations.email import platform_email_configured
from apps.makerspaces.models import Makerspace, TenantFrontend


class MakerspaceSerializer(serializers.ModelSerializer):
    telegram_bot_token = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    smtp_password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    telegram_bot_token_set = serializers.SerializerMethodField()
    smtp_password_set = serializers.SerializerMethodField()

    class Meta:
        model = Makerspace
        fields = [
            "id",
            "name",
            "public_code",
            "slug",
            "location",
            "public_inventory_enabled",
            "superadmin_access_enabled",
            "public_api_key",
            "cors_allowed_origins",
            "enabled_modules",
            "theme_config",
            "branding_config",
            "telegram_group_chat_id",
            "telegram_bot_token",
            "telegram_bot_token_set",
            "smtp_host",
            "smtp_port",
            "smtp_username",
            "smtp_password",
            "smtp_password_set",
            "smtp_use_tls",
            "smtp_use_ssl",
            "smtp_from_email",
            "default_loan_days",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "public_api_key",
            "telegram_bot_token_set",
            "smtp_password_set",
            "created_at",
            "updated_at",
        ]

    def get_telegram_bot_token_set(self, obj) -> bool:
        return bool(obj.telegram_bot_token)

    def get_smtp_password_set(self, obj) -> bool:
        return bool(obj.smtp_password)

    def validate_public_code(self, value):
        return value.upper()

    def validate_default_loan_days(self, value):
        if value < 1:
            raise serializers.ValidationError("Default loan days must be at least 1.")
        return value

    def update(self, instance, validated_data):
        telegram_bot_token = validated_data.pop("telegram_bot_token", None)
        smtp_password = validated_data.pop("smtp_password", None)
        new_flag = validated_data.pop("superadmin_access_enabled", None)
        with transaction.atomic():
            locked = Makerspace.objects.select_for_update().get(pk=instance.pk)
            actor = self.context["request"].user
            is_superadmin = actor.is_superuser or actor.role == User.Role.SUPERADMIN
            if new_flag is not None and new_flag != locked.superadmin_access_enabled:
                if new_flag is True and is_superadmin:
                    raise serializers.ValidationError(
                        {
                            "superadmin_access_enabled": (
                                "Only the makerspace admin can re-enable superadmin access."
                            )
                        }
                    )
                if new_flag is False and not platform_email_configured():
                    raise serializers.ValidationError(
                        {
                            "superadmin_access_enabled": (
                                "Configure Platform Email before disabling superadmin access, "
                                "so password recovery remains possible."
                            )
                        }
                    )
                locked.superadmin_access_enabled = new_flag
            for field, value in validated_data.items():
                setattr(locked, field, value)
            if telegram_bot_token:
                locked.set_telegram_bot_token(telegram_bot_token)
            if smtp_password:
                locked.set_smtp_password(smtp_password)
            locked.save()
            return locked


class MakerspaceSwitcherSerializer(serializers.ModelSerializer):
    """Minimal makerspace row for the staff console switcher.

    Print managers (MANAGE_PRINTING only, no VIEW_INVENTORY) need to pick their
    makerspace but must NOT see the full config the integration/settings views
    expose (public_api_key, CORS origins, SMTP host/username, module/theme
    config). This exposes only what the React console reads to render the
    switcher + header. telegram_group_chat_id is configuration, not a secret."""

    class Meta:
        model = Makerspace
        fields = [
            "id",
            "name",
            "public_code",
            "slug",
            "telegram_group_chat_id",
        ]
        read_only_fields = fields


class MakerspaceDisabledRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Makerspace
        fields = [
            "id",
            "name",
            "slug",
            "public_code",
            "location",
            "superadmin_access_enabled",
        ]
        read_only_fields = fields


class ReturnPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = Makerspace
        fields = ["id", "default_loan_days"]
        read_only_fields = ["id"]

    def validate_default_loan_days(self, value):
        if value < 1:
            raise serializers.ValidationError("Default loan days must be at least 1.")
        return value


class TenantFrontendSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantFrontend
        fields = [
            "id",
            "makerspace",
            "token",
            "hostname",
            "frontend_type",
            "allowed_origins",
            "enabled_modules",
            "theme_config",
            "branding_config",
            "is_primary",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "makerspace", "token", "created_at", "updated_at"]
