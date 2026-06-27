import re

from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import User
from apps.inventory import public_image_storage
from apps.integrations.email import platform_email_configured
from apps.integrations.smtp_validation import validate_smtp_settings
from apps.makerspaces.models import (
    Makerspace,
    default_branding_config,
    normalize_frontend_domain,
)
from apps.makerspaces.validators import validate_google_maps_url

# Bare hostname (DNS labels); allows "localhost" and "alpha-lab.example.com",
# rejects schemes, paths, ports, spaces, and empty labels.
_HOSTNAME_RE = re.compile(
    r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$"
)


class MakerspaceSerializer(serializers.ModelSerializer):
    frontend_domain = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=255,
    )
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
    logo_url = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    # Optional public-name override stored under branding_config["display_name"].
    # Blank => public pages fall back to the registered makerspace name. Written
    # through this dedicated, validated field (not the whole branding_config blob)
    # so we only touch the one key under the row lock and never clobber the rest.
    public_display_name = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        max_length=200,
        trim_whitespace=True,
    )

    class Meta:
        model = Makerspace
        fields = [
            "id",
            "name",
            "public_code",
            "slug",
            "location",
            "map_url",
            "public_inventory_enabled",
            "public_stats_enabled",
            "public_print_status_lookup_policy",
            "superadmin_access_enabled",
            "staff_notifications_enabled",
            "logo_key",
            "logo_url",
            "cover_image_key",
            "cover_image_url",
            "frontend_domain",
            "hidden_from_central_directory",
            "public_api_key",
            "cors_allowed_origins",
            "enabled_modules",
            "theme_config",
            "branding_config",
            "public_display_name",
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
            "logo_key",
            "logo_url",
            "cover_image_key",
            "cover_image_url",
            "telegram_bot_token_set",
            "smtp_password_set",
            # branding_config is returned (so the settings form can seed the
            # current display-name override) but only written via the validated
            # public_display_name field, never as an unchecked whole-blob PATCH.
            "branding_config",
            "created_at",
            "updated_at",
        ]

    def get_telegram_bot_token_set(self, obj) -> bool:
        return bool(obj.telegram_bot_token)

    def get_smtp_password_set(self, obj) -> bool:
        return bool(obj.smtp_password)

    @extend_schema_field({"type": "string", "format": "uri", "nullable": True})
    def get_logo_url(self, obj):
        return public_image_storage.public_url(obj.logo_key) or None

    @extend_schema_field({"type": "string", "format": "uri", "nullable": True})
    def get_cover_image_url(self, obj):
        return public_image_storage.public_url(obj.cover_image_key) or None

    def validate_public_code(self, value):
        return value.upper()

    def validate_map_url(self, value):
        validate_google_maps_url(value)
        return value

    def validate_default_loan_days(self, value):
        if value < 1:
            raise serializers.ValidationError("Default loan days must be at least 1.")
        return value

    def validate(self, attrs):
        if "frontend_domain" in attrs:
            raw_domain = attrs.get("frontend_domain")
            normalized_domain = normalize_frontend_domain(raw_domain)
            attrs["frontend_domain"] = normalized_domain
            if normalized_domain is None:
                # A non-empty input that normalized to nothing was malformed.
                if (raw_domain or "").strip():
                    raise serializers.ValidationError(
                        {"frontend_domain": "Enter a valid domain, e.g. alphamakerspace.com."}
                    )
                attrs["hidden_from_central_directory"] = False
                return attrs
            if not _HOSTNAME_RE.match(normalized_domain):
                raise serializers.ValidationError(
                    {"frontend_domain": "Enter a valid domain, e.g. alphamakerspace.com."}
                )

            queryset = Makerspace.objects.filter(frontend_domain__iexact=normalized_domain)
            if self.instance is not None:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError(
                    {
                        "frontend_domain": (
                            "A makerspace with this frontend domain already exists."
                        )
                    }
                )

        effective_domain = attrs.get(
            "frontend_domain",
            self.instance.frontend_domain if self.instance is not None else None,
        )
        effective_hidden = attrs.get(
            "hidden_from_central_directory",
            self.instance.hidden_from_central_directory if self.instance is not None else False,
        )
        if effective_hidden and not effective_domain:
            raise serializers.ValidationError(
                {
                    "hidden_from_central_directory": (
                        "A frontend domain is required to hide a makerspace from the central directory."
                    )
                }
            )
        validate_smtp_settings(attrs, self.instance)
        return attrs

    def create(self, validated_data):
        # public_display_name is a non-model write field; the default
        # ModelSerializer.create would pass it to Makerspace.objects.create and
        # 500. Fold it into branding_config["display_name"] instead.
        public_display_name = validated_data.pop("public_display_name", None)
        if public_display_name is not None:
            branding = default_branding_config()
            branding["display_name"] = public_display_name
            validated_data["branding_config"] = branding
        return super().create(validated_data)

    def update(self, instance, validated_data):
        missing = object()
        telegram_bot_token = validated_data.pop("telegram_bot_token", missing)
        smtp_password = validated_data.pop("smtp_password", missing)
        public_display_name = validated_data.pop("public_display_name", missing)
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
            if public_display_name is not missing:
                # Merge into the FRESH locked row's branding_config so we never
                # overwrite support_email/support_url from a stale client copy.
                branding = dict(locked.branding_config or {})
                branding["display_name"] = public_display_name
                locked.branding_config = branding
            if telegram_bot_token is not missing:
                locked.set_telegram_bot_token(telegram_bot_token)
            if smtp_password is not missing:
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
