from rest_framework import serializers

from apps.apiclients.models import ApiClient
from apps.makerspaces.models import Makerspace


class ApiClientSerializer(serializers.ModelSerializer):
    client_secret = serializers.CharField(read_only=True)
    backend_base_url = serializers.SerializerMethodField()
    public_api_base_url = serializers.SerializerMethodField()
    public_makerspace_code = serializers.CharField(
        source="makerspace.public_code",
        read_only=True,
    )

    class Meta:
        model = ApiClient
        fields = [
            "id",
            "label",
            "client_id",
            "client_secret",
            "client_type",
            "scopes",
            "rate_limit_tier",
            "makerspace",
            "public_makerspace_code",
            "allowed_origins",
            "backend_base_url",
            "public_api_base_url",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "client_id",
            "client_secret",
            "makerspace",
            "public_makerspace_code",
            "backend_base_url",
            "public_api_base_url",
            "created_at",
            "updated_at",
        ]

    def validate_allowed_origins(self, value):
        if not value:
            raise serializers.ValidationError("At least one frontend origin is required.")
        for origin in value:
            if not isinstance(origin, str) or not origin.startswith(("http://", "https://")):
                raise serializers.ValidationError("Origins must be exact http(s) URLs.")
        return value

    def validate(self, attrs):
        client_type = attrs.get("client_type") or getattr(self.instance, "client_type", "server")
        scopes = attrs.get("scopes", getattr(self.instance, "scopes", []))
        if client_type == "browser":
            forbidden = {"inventory:write", "requests:review", "admin:write", "qr:manage"}
            if forbidden.intersection(set(scopes or [])):
                raise serializers.ValidationError(
                    {"scopes": "Browser clients may only use public/read scopes."}
                )
        return attrs

    def get_backend_base_url(self, _obj) -> str:
        request = self.context.get("request")
        return request.build_absolute_uri("/").rstrip("/") if request else ""

    def get_public_api_base_url(self, obj) -> str:
        request = self.context.get("request")
        if not request:
            return ""
        code = obj.makerspace.public_code if obj.makerspace_id else ""
        return request.build_absolute_uri(f"/api/v1/public/{code}/").rstrip("/")


class ApiIntegrationSettingsSerializer(serializers.ModelSerializer):
    public_api_key = serializers.CharField(read_only=True)
    cors_allowed_origins = serializers.ListField(
        child=serializers.CharField(),
        read_only=True,
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

    class Meta:
        model = Makerspace
        fields = [
            "public_code",
            "public_api_key",
            "cors_allowed_origins",
            "telegram_group_chat_id",
            "telegram_bot_token",
            "telegram_bot_token_set",
            "smtp_host",
            "smtp_port",
            "smtp_username",
            "smtp_password",
            "smtp_password_set",
            "smtp_use_tls",
            "smtp_from_email",
            "default_loan_days",
        ]
        read_only_fields = [
            "public_code",
            "public_api_key",
            "cors_allowed_origins",
            "telegram_bot_token_set",
            "smtp_password_set",
        ]

    def get_telegram_bot_token_set(self, obj) -> bool:
        return bool(obj.telegram_bot_token)

    def get_smtp_password_set(self, obj) -> bool:
        return bool(obj.smtp_password)

    def validate_default_loan_days(self, value):
        if value < 1:
            raise serializers.ValidationError("Default loan days must be at least 1.")
        return value

    def update(self, instance, validated_data):
        telegram_bot_token = validated_data.pop("telegram_bot_token", None)
        smtp_password = validated_data.pop("smtp_password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if telegram_bot_token:
            instance.set_telegram_bot_token(telegram_bot_token)
        if smtp_password:
            instance.set_smtp_password(smtp_password)
        instance.save()
        return instance
