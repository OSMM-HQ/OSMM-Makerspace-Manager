from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integrations.email import email_enabled


class PublicConfigSerializer(serializers.Serializer):
    email_enabled = serializers.BooleanField()


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
        return Response({"email_enabled": email_enabled()})
