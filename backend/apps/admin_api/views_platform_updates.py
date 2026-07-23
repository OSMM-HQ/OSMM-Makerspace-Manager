from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.admin_api.permissions import IsActiveSuperAdmin
from apps.audit import services as audit
from apps.updates import services
from apps.updates.models import PlatformUpdateSettings


class PlatformUpdateSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformUpdateSettings
        fields = (
            "automatic_updates_enabled",
            "status",
            "current_version",
            "available_version",
            "target_version",
            "update_requested_at",
            "last_checked_at",
            "last_updated_at",
            "last_backup_at",
            "last_backup_name",
            "last_error",
            "updated_at",
        )
        read_only_fields = (
            "status",
            "current_version",
            "available_version",
            "target_version",
            "update_requested_at",
            "last_checked_at",
            "last_updated_at",
            "last_backup_at",
            "last_backup_name",
            "last_error",
            "updated_at",
        )


@extend_schema(
    tags=["Platform"],
    summary="Retrieve or update automatic production update settings",
)
class PlatformUpdateSettingsView(generics.RetrieveUpdateAPIView):
    serializer_class = PlatformUpdateSettingsSerializer
    permission_classes = [IsActiveSuperAdmin]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return PlatformUpdateSettings.load()

    def perform_update(self, serializer):
        instance = serializer.save()
        audit.record(
            self.request.user,
            "platform.update_settings_updated",
            target=instance,
            meta={
                "automatic_updates_enabled": instance.automatic_updates_enabled,
            },
        )


@extend_schema(
    tags=["Platform"],
    summary="Queue the latest production release for installation",
    request=None,
    responses={status.HTTP_202_ACCEPTED: PlatformUpdateSettingsSerializer},
)
class PlatformUpdateRequestView(APIView):
    permission_classes = [IsActiveSuperAdmin]

    def post(self, request):
        instance = services.queue_update()
        audit.record(
            request.user,
            "platform.update_requested",
            target=instance,
        )
        return Response(
            PlatformUpdateSettingsSerializer(instance).data,
            status=status.HTTP_202_ACCEPTED,
        )
