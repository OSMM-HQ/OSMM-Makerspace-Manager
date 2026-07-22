from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import generics

from apps.admin_api.permissions import IsActiveSuperAdmin
from apps.admin_api.serializers_payments import PlatformStripeConnectSettingsSerializer
from apps.audit import services as audit
from apps.makerspaces.domain_verification import is_self_host
from apps.payments.models import PlatformStripeConnectSettings


@extend_schema(
    tags=["Platform"],
    summary="Retrieve or update platform Stripe Connect settings",
)
class PlatformStripeConnectSettingsView(generics.RetrieveUpdateAPIView):
    serializer_class = PlatformStripeConnectSettingsSerializer
    permission_classes = [IsActiveSuperAdmin]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        if is_self_host():
            raise Http404
        return PlatformStripeConnectSettings.load()

    def perform_update(self, serializer):
        instance = serializer.save()
        audit.record(
            self.request.user,
            "platform.stripe_connect_settings_updated",
            target=instance,
        )
