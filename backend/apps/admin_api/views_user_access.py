from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.admin_api.permissions import (
    IsActiveStaff,
    IsActiveSuperAdmin,
    require_user_access_mutation,
)
from apps.admin_api.serializers_users import (
    ResetPasswordRequestSerializer,
    ResetPasswordResponseSerializer,
    RestrictUserSerializer,
    UserSerializer,
)
from apps.admin_api.services_user_access import reset_user_password
from apps.audit import services as audit
from apps.openapi import RESTRICT_USER_EXAMPLE


class RestrictUserView(APIView):
    permission_classes = [IsActiveSuperAdmin]

    @extend_schema(
        tags=["Admin users"],
        summary="Restrict or suspend a user",
        request=RestrictUserSerializer,
        responses={200: UserSerializer},
        examples=[RESTRICT_USER_EXAMPLE],
    )
    def post(self, request, pk, *args, **kwargs):
        user = get_object_or_404(User, pk=pk)
        require_user_access_mutation(request.user, user)
        serializer = RestrictUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user.access_status = serializer.validated_data["status"]
        user.restriction_reason = serializer.validated_data["reason"]
        user.save(update_fields=["access_status", "restriction_reason"])
        audit.record(
            request.user,
            "user.access_restricted",
            target=user,
            meta={"status": user.access_status, "reason": user.restriction_reason},
        )
        return Response(UserSerializer(user).data)


class ResetUserPasswordView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Admin users"],
        summary="Reset a staff user's password (temp + force change)",
        request=ResetPasswordRequestSerializer,
        responses={200: ResetPasswordResponseSerializer},
    )
    def post(self, request, pk, *args, **kwargs):
        result = reset_user_password(
            request.user,
            pk,
            data=request.data,
        )
        return Response(
            ResetPasswordResponseSerializer(
                {
                    "username": result.user.username,
                    "temporary_password": result.temporary_password,
                }
            ).data
        )


class RestoreUserAccessView(APIView):
    permission_classes = [IsActiveSuperAdmin]

    @extend_schema(tags=["Admin users"], summary="Restore user access", request=None, responses={200: UserSerializer})
    def post(self, request, pk, *args, **kwargs):
        user = get_object_or_404(User, pk=pk)
        require_user_access_mutation(request.user, user)
        user.access_status = User.AccessStatus.ACTIVE
        user.restriction_reason = ""
        user.save(update_fields=["access_status", "restriction_reason"])
        audit.record(request.user, "user.access_restored", target=user)
        return Response(UserSerializer(user).data)
