from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils.crypto import get_random_string
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.accounts import rbac
from apps.accounts.models import User
from apps.admin_api.permissions import IsActiveStaff
from apps.admin_api.serializers_users import (
    AuditLogSerializer,
    StaffCreateSerializer,
    StaffMembershipSerializer,
)
from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.makerspaces.models import Makerspace, MakerspaceMembership


@extend_schema(tags=["Admin users"], summary="List or create staff memberships")
class StaffListCreateView(generics.ListCreateAPIView):
    serializer_class = StaffMembershipSerializer
    permission_classes = [IsActiveStaff]

    def get_queryset(self):
        target_role = self.kwargs["role"]
        scope = rbac.makerspaces_for_action(self.request.user, rbac.Action.MANAGE_STAFF)
        queryset = MakerspaceMembership.objects.select_related("user", "makerspace").filter(
            role=target_role
        )
        if scope is rbac.ALL:
            queryset = rbac.hide_from_superadmin(
                self.request.user,
                queryset,
                field="makerspace_id",
            )
            return queryset.order_by("user__username")
        if target_role in (
            MakerspaceMembership.Role.PRINT_MANAGER,
            MakerspaceMembership.Role.INVENTORY_MANAGER,
        ):
            manage_scope = rbac.makerspaces_for_action(
                self.request.user,
                rbac.Action.MANAGE_MAKERSPACE,
            )
            if manage_scope is rbac.ALL:
                return queryset.order_by("user__username")
            return queryset.filter(makerspace_id__in=manage_scope).order_by(
                "user__username"
            )
        return queryset.none()

    def create(self, request, *args, **kwargs):
        serializer = StaffCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        target_role = self.kwargs["role"]
        if data["role"] != target_role:
            raise ValidationError({"role": "Role does not match endpoint."})
        makerspace_id = data["makerspace_id"]
        if not _can_create_staff_role(request.user, target_role, makerspace_id):
            raise PermissionDenied()
        # A superadmin can target any makerspace_id, including a nonexistent one. Validate
        # before writing: otherwise get_or_create commits the user, then the membership FK
        # fails -> 500 and an orphaned staff account. Wrap both writes in one transaction so
        # a membership failure rolls back the user creation too.
        makerspace = Makerspace.objects.filter(pk=makerspace_id).first()
        if not makerspace:
            raise ValidationError({"makerspace_id": "Makerspace does not exist."})
        # An archived makerspace is soft-deleted / operationally unreachable; never attach
        # new staff to it (the superadmin branch of _can_create_staff_role bypasses rbac scope).
        if makerspace.archived_at is not None:
            raise ValidationError({"makerspace_id": "Makerspace is archived."})
        is_break_glass = (
            (request.user.is_superuser or request.user.role == User.Role.SUPERADMIN)
            and not makerspace.superadmin_access_enabled
        )
        user_defaults = {
            "email": data.get("email", ""),
            "first_name": data.get("first_name", ""),
            "last_name": data.get("last_name", ""),
            "role": _global_role_for_membership(target_role),
            "password": make_password(data.get("password") or get_random_string(32)),
        }
        with transaction.atomic():
            if is_break_glass:
                errors = {}
                if User.objects.filter(username=data["username"]).exists():
                    errors["username"] = "A user with that username already exists."
                email = data.get("email", "")
                if email and User.objects.filter(email__iexact=email).exists():
                    errors["email"] = "A user with that email already exists."
                if errors:
                    raise ValidationError(errors)
                user = User.objects.create(username=data["username"], **user_defaults)
                membership = MakerspaceMembership.objects.create(
                    user=user,
                    makerspace=makerspace,
                    role=target_role,
                )
                created = True
            else:
                user, created = User.objects.get_or_create(
                    username=data["username"],
                    defaults=user_defaults,
                )
                membership, _ = MakerspaceMembership.objects.update_or_create(
                    user=user,
                    makerspace_id=makerspace_id,
                    defaults={"role": target_role},
                )
        audit.record(
            request.user,
            (
                "superadmin.break_glass_space_manager_created"
                if is_break_glass
                else "staff.created" if created else "staff.membership_updated"
            ),
            makerspace=membership.makerspace,
            target=user,
            meta={"membership_role": target_role},
        )
        return Response(StaffMembershipSerializer(membership).data, status=201)


def _global_role_for_membership(target_role):
    if target_role == MakerspaceMembership.Role.SPACE_MANAGER:
        return User.Role.SPACE_MANAGER
    if target_role == MakerspaceMembership.Role.GUEST_ADMIN:
        return User.Role.GUEST_ADMIN
    if target_role == MakerspaceMembership.Role.INVENTORY_MANAGER:
        return User.Role.REQUESTER
    return User.Role.REQUESTER


def _can_create_staff_role(user, target_role, makerspace_id):
    if user.is_superuser or user.role == User.Role.SUPERADMIN:
        if int(makerspace_id) in rbac.superadmin_hidden_makerspace_ids():
            return target_role == MakerspaceMembership.Role.SPACE_MANAGER
        return True
    if target_role not in (
        MakerspaceMembership.Role.PRINT_MANAGER,
        MakerspaceMembership.Role.INVENTORY_MANAGER,
    ):
        return False
    return rbac.can(user, rbac.Action.MANAGE_MAKERSPACE, makerspace_id)


class AuditLogPagination(PageNumberPagination):
    page_size = 24


@extend_schema(tags=["Admin users"], summary="List audit log entries", parameters=[
    OpenApiParameter("makerspace", int, OpenApiParameter.QUERY), OpenApiParameter("action", str, OpenApiParameter.QUERY),
    OpenApiParameter("target_type", str, OpenApiParameter.QUERY), OpenApiParameter("target_id", str, OpenApiParameter.QUERY),
])
class AuditLogListView(generics.ListAPIView):
    serializer_class = AuditLogSerializer
    permission_classes = [IsActiveStaff]
    pagination_class = AuditLogPagination

    def get_queryset(self):
        queryset = AuditLog.objects.select_related("actor", "makerspace").order_by("-created_at")
        queryset = rbac.scope_by_action(self.request.user, rbac.Action.VIEW_AUDIT, queryset)
        queryset = rbac.hide_from_superadmin(self.request.user, queryset, field="makerspace_id")
        archived = rbac.archived_makerspace_ids()
        if archived:
            queryset = queryset.exclude(makerspace_id__in=archived)
        makerspace_id = self.request.query_params.get("makerspace")
        action = self.request.query_params.get("action")
        target_type, target_id = (
            self.request.query_params.get("target_type"),
            self.request.query_params.get("target_id"),
        )
        filters = {}
        if makerspace_id:
            filters["makerspace_id"] = makerspace_id
        if action:
            filters["action"] = action
        if target_type:
            filters["target_type"] = target_type
        if target_id:
            filters["target_id"] = target_id
        if filters:
            queryset = queryset.filter(**filters)
        return queryset
