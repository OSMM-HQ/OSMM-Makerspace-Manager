from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.http import Http404
from django.utils.crypto import get_random_string
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

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
from apps.makerspaces import limits
from apps.makerspaces.models import Makerspace, MakerspaceMembership

# Roles a Space Manager (MANAGE_MAKERSPACE holder, non-superadmin) may assign, list, and
# revoke within their own makerspace scope. Deliberately excludes SPACE_MANAGER: an SM must
# never create another Space Manager or escalate toward superadmin (Part I non-escalation
# guard). Creating/assigning SPACE_MANAGER and every restrict/restore/reset existential
# guard stay superadmin-only.
_SM_DELEGABLE_ROLES = (
    MakerspaceMembership.Role.PRINT_MANAGER,
    MakerspaceMembership.Role.INVENTORY_MANAGER,
    MakerspaceMembership.Role.MACHINE_MANAGER,
    MakerspaceMembership.Role.GUEST_ADMIN,
)


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
        if target_role in _SM_DELEGABLE_ROLES:
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

    @extend_schema(request=StaffCreateSerializer, responses=StaffMembershipSerializer)
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
        actor_is_superadmin = (
            request.user.is_superuser or request.user.role == User.Role.SUPERADMIN
        )
        is_break_glass = (
            actor_is_superadmin and not makerspace.superadmin_access_enabled
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
                limits.check_quota(makerspace, "staff", adding=1)
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
                # Non-escalation guard (Part I): a Space Manager may create/assign only
                # delegable roles, and must never overwrite an existing SPACE_MANAGER
                # membership (which update_or_create below would silently rewrite). Locked +
                # re-checked INSIDE the transaction so a concurrent superadmin promotion to
                # SPACE_MANAGER can't be raced past this guard. Superadmin is unaffected.
                if not actor_is_superadmin:
                    existing_role = (
                        MakerspaceMembership.objects.select_for_update()
                        .filter(makerspace_id=makerspace_id, user=user)
                        .values_list("role", flat=True)
                        .first()
                    )
                    if existing_role is not None and existing_role not in _SM_DELEGABLE_ROLES:
                        raise PermissionDenied(
                            "Only a superadmin can change a Space Manager membership."
                        )
                has_active_membership = MakerspaceMembership.objects.filter(
                    user=user,
                    makerspace=makerspace,
                    user__is_active=True,
                    user__access_status=User.AccessStatus.ACTIVE,
                ).exists()
                if not has_active_membership and user.is_active and (
                    user.access_status == User.AccessStatus.ACTIVE
                ):
                    limits.check_quota(makerspace, "staff", adding=1)
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
        if rbac._id_in(makerspace_id, rbac.superadmin_hidden_makerspace_ids()):
            return target_role == MakerspaceMembership.Role.SPACE_MANAGER
        return True
    if target_role not in _SM_DELEGABLE_ROLES:
        return False
    return rbac.can(user, rbac.Action.MANAGE_MAKERSPACE, makerspace_id)


@extend_schema(
    tags=["Admin users"],
    summary="Revoke a staff membership",
    responses={204: None},
)
class MembershipRevokeView(APIView):
    """Remove a single makerspace membership (un-assign a delegable role).

    Scope contract (mirrors the create path's non-escalation model): a Space Manager may
    revoke ONLY delegable-role memberships within their MANAGE_MAKERSPACE scope; a superadmin
    may revoke any, except inside a superadmin-hidden makerspace (governance hard-block ->
    404). 404-before-403: out-of-scope existence is hidden as 404, a delegable-scope actor
    aiming at a SPACE_MANAGER gets 403.
    """

    permission_classes = [IsActiveStaff]

    def delete(self, request, pk):
        actor = request.user
        is_superadmin = actor.is_superuser or actor.role == User.Role.SUPERADMIN
        # Lock the membership row and run the authorization re-check + delete + audit in one
        # transaction: a concurrent promotion to SPACE_MANAGER must not slip past the role
        # guard, and a delete must never commit without its audit row.
        with transaction.atomic():
            membership = (
                MakerspaceMembership.objects.select_for_update()
                .select_related("makerspace", "user")
                .filter(pk=pk)
                .first()
            )
            if membership is None:
                raise Http404
            if is_superadmin:
                if rbac._id_in(
                    membership.makerspace_id, rbac.superadmin_hidden_makerspace_ids()
                ):
                    raise Http404
            else:
                if not rbac.can(
                    actor, rbac.Action.MANAGE_MAKERSPACE, membership.makerspace_id
                ):
                    raise Http404
                if membership.role not in _SM_DELEGABLE_ROLES:
                    raise PermissionDenied(
                        "Only a superadmin can revoke a Space Manager membership."
                    )
            makerspace, target_user, role = (
                membership.makerspace,
                membership.user,
                membership.role,
            )
            membership.delete()
            audit.record(
                actor,
                "staff.membership_revoked",
                makerspace=makerspace,
                target=target_user,
                meta={"membership_role": role},
            )
        return Response(status=204)


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
