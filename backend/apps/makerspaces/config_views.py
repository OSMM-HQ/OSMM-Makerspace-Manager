from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integrations.email import email_enabled


class PublicConfigSerializer(serializers.Serializer):
    email_enabled = serializers.BooleanField()
    public_image_max_bytes = serializers.IntegerField()
    social_auth = serializers.DictField(required=False)


class PublicConfigView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        tags=["Platform"],
        summary="Return frontend-safe platform configuration",
        responses={200: PublicConfigSerializer},
    )
    def get(self, request, *args, **kwargs):
        payload = {
            "email_enabled": email_enabled(),
            "public_image_max_bytes": settings.PUBLIC_IMAGE_MAX_BYTES,
        }
        from apps.accounts.models_social import PlatformSocialAuthSettings

        social = PlatformSocialAuthSettings.objects.filter(pk=1).first()
        configured = {}
        if social and social.google_web_client_id:
            configured["google"] = {
                "enabled": True,
                "web_client_id": social.google_web_client_id,
            }
        if social and social.apple_service_id:
            configured["apple"] = {
                "enabled": True,
                "service_id": social.apple_service_id,
            }
        if configured:
            payload["social_auth"] = configured
        return Response(payload)
