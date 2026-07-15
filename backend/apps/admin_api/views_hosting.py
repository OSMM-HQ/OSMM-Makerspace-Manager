from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveSuperAdmin
from apps.admin_api.serializers_makerspaces import MakerspaceSerializer
from apps.makerspaces.models import Makerspace
from apps.makerspaces.provisioning import provision_subdomain


class ProvisionSubdomainRequestSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=63, trim_whitespace=True)


class ProvisionSubdomainValidationErrorSerializer(serializers.Serializer):
    label = serializers.ListField(child=serializers.CharField())


class HostingErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


@extend_schema(
    tags=["Admin makerspaces"],
    summary="Provision a platform subdomain for a makerspace",
    request=ProvisionSubdomainRequestSerializer,
    responses={
        200: MakerspaceSerializer,
        400: OpenApiResponse(
            response=ProvisionSubdomainValidationErrorSerializer,
            description="Invalid or unavailable platform subdomain label.",
        ),
        403: OpenApiResponse(
            response=HostingErrorSerializer,
            description="Active superadmin access is required.",
        ),
        404: OpenApiResponse(
            response=HostingErrorSerializer,
            description="Makerspace not found.",
        ),
    },
)
class MakerspaceProvisionSubdomainView(APIView):
    permission_classes = [IsActiveSuperAdmin]
    http_method_names = ["post", "options"]

    def post(self, request, makerspace_id, *args, **kwargs):
        serializer = ProvisionSubdomainRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        makerspace = get_object_or_404(
            rbac.scope_by_action(
                request.user,
                rbac.Action.MANAGE_MAKERSPACE,
                Makerspace.objects.filter(archived_at__isnull=True),
                field="id",
            ),
            pk=makerspace_id,
        )
        try:
            provisioned = provision_subdomain(
                makerspace,
                serializer.validated_data["label"],
                request.user,
            )
        except DjangoValidationError as exc:
            raise ValidationError({"label": exc.messages}) from exc
        return Response(MakerspaceSerializer(provisioned, context={"request": request}).data)
