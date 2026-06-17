from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.utils.crypto import get_random_string
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.accounts.models import User
from apps.admin_api.permissions import (
    hidden_space_manager_reset_break_glass,
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
from apps.audit import services as audit
from apps.makerspaces.models import MakerspaceMembership
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
        actor = request.user
        is_superadmin = actor.is_superuser or actor.role == User.Role.SUPERADMIN
        target = _target_for_reset(actor, pk, is_superadmin)
        if target.is_superuser or target.role == User.Role.SUPERADMIN:
            raise PermissionDenied("Cannot reset a superadmin's password here.")

        break_glass_password_reset = False
        if is_superadmin:
            break_glass_password_reset = hidden_space_manager_reset_break_glass(target)
        _require_non_superadmin_reset_scope(actor, target, is_superadmin)

        serializer = ResetPasswordRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        password = _validated_or_generated_password(serializer, target)
        target.set_password(password)
        target.must_change_password = True
        target.save(update_fields=["password", "must_change_password"])

        from apps.accounts.views import _blacklist_outstanding_tokens

        _blacklist_outstanding_tokens(target)
        audit.record(
            actor,
            (
                "superadmin.break_glass_space_manager_password_reset"
                if break_glass_password_reset
                else "user.password_reset"
            ),
            target=target,
            meta={"by_superadmin": is_superadmin},
        )
        return Response(
            ResetPasswordResponseSerializer(
                {"username": target.username, "temporary_password": password}
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


def _target_for_reset(actor, pk, is_superadmin):
    if is_superadmin:
        return get_object_or_404(User, pk=pk)
    scope = rbac.makerspaces_for_action(actor, rbac.Action.MANAGE_MAKERSPACE)
    base = User.objects.all()
    if scope is not rbac.ALL:
        base = base.filter(makerspace_memberships__makerspace_id__in=scope).distinct()
    return get_object_or_404(base, pk=pk)


def _require_non_superadmin_reset_scope(actor, target, is_superadmin):
    if is_superadmin:
        return
    memberships = MakerspaceMembership.objects.filter(user=target)
    if not memberships.exists():
        raise PermissionDenied("You can only reset staff in your makerspaces.")
    scope = rbac.makerspaces_for_action(actor, rbac.Action.MANAGE_MAKERSPACE)
    if scope is not rbac.ALL:
        target_ms = set(memberships.values_list("makerspace_id", flat=True))
        if not target_ms.issubset(scope):
            raise PermissionDenied(
                "This user also belongs to a makerspace outside your authority."
            )
    if memberships.filter(role=MakerspaceMembership.Role.SPACE_MANAGER).exists():
        raise PermissionDenied("Cannot reset another Space Manager's password.")


def _validated_or_generated_password(serializer, target):
    password = serializer.validated_data.get("password")
    if password:
        try:
            validate_password(password, user=target)
        except DjangoValidationError as exc:
            raise ValidationError({"password": list(exc.messages)}) from exc
        return password
    for _ in range(5):
        candidate = get_random_string(12)
        try:
            validate_password(candidate, user=target)
            return candidate
        except DjangoValidationError:
            continue
    return get_random_string(16)
