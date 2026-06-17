from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.accounts import rbac
from apps.accounts.models import User
from apps.admin_api.permissions import IsActiveStaff, require_action
from apps.admin_api.serializers_makerspaces import (
    MakerspaceDisabledRowSerializer,
    MakerspaceSerializer,
    MakerspaceSwitcherSerializer,
    ReturnPolicySerializer,
    TenantFrontendSerializer,
)
from apps.audit import services as audit
from apps.makerspaces.guards import require_module
from apps.makerspaces.models import Makerspace, TenantFrontend
from apps.makerspaces.origin_scope import origin_scoped_makerspace_id


@extend_schema(tags=["Admin makerspaces"], summary="List or create makerspaces")
class MakerspaceListCreateView(generics.ListCreateAPIView):
    serializer_class = MakerspaceSerializer
    permission_classes = [IsActiveStaff]
    pagination_class = None

    def get_queryset(self):
        # The staff console switcher must list a makerspace for any staff role
        # that has a surface there — including print managers, who hold only
        # MANAGE_PRINTING (no VIEW_INVENTORY). Scope by the union so a pure print
        # manager isn't stuck on an empty list / "No makerspace" screen. Create
        # (POST) stays superadmin-only in perform_create, so widening the read
        # scope here doesn't grant anyone new write access.
        queryset = Makerspace.objects.filter(archived_at__isnull=True)
        actor = self.request.user
        origin_scope = origin_scoped_makerspace_id(self.request)
        if actor.is_superuser or actor.role == User.Role.SUPERADMIN:
            # Governance list: the superadmin still sees hidden, non-archived
            # makerspaces (rendered as slim disabled rows in list() below) so a
            # hard-hidden space stays discoverable for break-glass. Archived
            # spaces are omitted from the React console and remain visible only
            # in /control/.
            if origin_scope is not None:
                queryset = queryset.filter(id=origin_scope)
            return queryset.order_by("name")
        scope = rbac.makerspaces_for_actions(
            actor,
            rbac.Action.VIEW_INVENTORY,
            rbac.Action.MANAGE_PRINTING,
        )
        if not scope:
            return queryset.none()
        queryset = queryset.filter(id__in=scope)
        if origin_scope is not None:
            queryset = queryset.filter(id=origin_scope)
        return queryset.order_by("name")

    def list(self, request, *args, **kwargs):
        # Serialize PER ROW: the full makerspace config (public_api_key, CORS
        # origins, SMTP host/username, module/theme config) is only for rows the
        # user can VIEW_INVENTORY. Rows reachable solely via MANAGE_PRINTING (a
        # print manager populating the switcher) get the slim serializer. A
        # mixed-role user (VIEW_INVENTORY in A, print-only in B) therefore sees A
        # in full and B slim — choosing one serializer for the whole list would
        # leak B's config. Settings writes stay MANAGE_MAKERSPACE-gated elsewhere.
        view_scope = rbac.makerspaces_for_action(request.user, rbac.Action.VIEW_INVENTORY)
        context = self.get_serializer_context()
        is_superadmin = request.user.is_superuser or request.user.role == User.Role.SUPERADMIN
        hidden_ids = rbac.superadmin_hidden_makerspace_ids() if is_superadmin else set()

        def serialize(makerspace):
            if is_superadmin and makerspace.id in hidden_ids:
                return MakerspaceDisabledRowSerializer(makerspace, context=context).data
            can_view = view_scope is rbac.ALL or makerspace.id in view_scope
            serializer = MakerspaceSerializer if can_view else MakerspaceSwitcherSerializer
            return serializer(makerspace, context=context).data

        return Response([serialize(item) for item in self.filter_queryset(self.get_queryset())])

    def perform_create(self, serializer):
        if not (self.request.user.is_superuser or self.request.user.role == User.Role.SUPERADMIN):
            raise PermissionDenied()
        instance = serializer.save(created_by=self.request.user)
        audit.record(
            self.request.user,
            "makerspace.created",
            makerspace=instance,
            target=instance,
        )


@extend_schema(tags=["Admin makerspaces"], summary="Retrieve or update a makerspace")
class MakerspaceDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = MakerspaceSerializer
    permission_classes = [IsActiveStaff]
    http_method_names = ["get", "patch", "head", "options"]

    def get_serializer_class(self):
        # self.request is None during schema generation; the user may be Anonymous.
        if self.request is not None and self.request.method == "GET":
            makerspace = getattr(self, "_makerspace_object", None)
            actor = getattr(self.request, "user", None)
            is_superadmin = bool(
                actor
                and getattr(actor, "is_authenticated", False)
                and (actor.is_superuser or getattr(actor, "role", None) == User.Role.SUPERADMIN)
            )
            hidden_ids = rbac.superadmin_hidden_makerspace_ids() if is_superadmin else set()
            if makerspace is not None and makerspace.id in hidden_ids:
                return MakerspaceDisabledRowSerializer
        return MakerspaceSerializer

    def get_queryset(self):
        actor = self.request.user
        is_superadmin = actor.is_superuser or actor.role == User.Role.SUPERADMIN
        queryset = Makerspace.objects.filter(archived_at__isnull=True)
        if self.request.method == "GET" and is_superadmin:
            # Slim disabled-row visibility (get_serializer_class serves the slim
            # serializer for a hidden makerspace) so the superadmin can still see a
            # hard-hidden space exists for break-glass. PATCH stays RBAC-scoped, so
            # a superadmin still can't edit/re-enable a hidden makerspace.
            return queryset
        action = (
            rbac.Action.MANAGE_MAKERSPACE
            if self.request.method == "PATCH"
            else rbac.Action.VIEW_INVENTORY
        )
        return rbac.scope_by_action(self.request.user, action, queryset, field="id")

    def get_object(self):
        self._makerspace_object = super().get_object()
        return self._makerspace_object

    def perform_update(self, serializer):
        was_enabled = serializer.instance.superadmin_access_enabled
        instance = serializer.save()
        audit.record(
            self.request.user,
            "makerspace.updated",
            makerspace=instance,
            target=instance,
        )
        if was_enabled != instance.superadmin_access_enabled:
            audit.record(
                self.request.user,
                "makerspace.superadmin_access_changed",
                makerspace=instance,
                target=instance,
                meta={"enabled": instance.superadmin_access_enabled},
            )


@extend_schema(tags=["Admin makerspaces"], summary="Retrieve or update return policy")
class ReturnPolicyView(generics.RetrieveUpdateAPIView):
    serializer_class = ReturnPolicySerializer
    permission_classes = [IsActiveStaff]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        makerspace_id = self.kwargs["makerspace_id"]
        require_action(self.request.user, rbac.Action.ACCEPT_REQUEST, makerspace_id)
        return get_object_or_404(Makerspace, pk=makerspace_id)

    def perform_update(self, serializer):
        instance = serializer.save()
        audit.record(
            self.request.user,
            "makerspace.return_policy_updated",
            makerspace=instance,
            target=instance,
            meta={"default_loan_days": instance.default_loan_days},
        )


@extend_schema(tags=["Tenant bootstrap"], summary="List or create registered tenant frontends")
class TenantFrontendListCreateView(generics.ListCreateAPIView):
    serializer_class = TenantFrontendSerializer
    permission_classes = [IsActiveStaff]

    def get_queryset(self):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(makerspace_id, "staff_admin")
        require_action(self.request.user, rbac.Action.MANAGE_MAKERSPACE, makerspace_id)
        return TenantFrontend.objects.filter(makerspace_id=makerspace_id).order_by("frontend_type", "hostname")

    def perform_create(self, serializer):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(makerspace_id, "staff_admin")
        require_action(self.request.user, rbac.Action.MANAGE_MAKERSPACE, makerspace_id)
        frontend = serializer.save(makerspace_id=makerspace_id, created_by=self.request.user)
        audit.record(
            self.request.user,
            "tenant_frontend.created",
            makerspace=frontend.makerspace,
            target=frontend,
        )


@extend_schema(tags=["Tenant bootstrap"], summary="Retrieve or update registered tenant frontend")
class TenantFrontendDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = TenantFrontendSerializer
    permission_classes = [IsActiveStaff]
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return rbac.scope_by_action(
            self.request.user,
            rbac.Action.MANAGE_MAKERSPACE,
            TenantFrontend.objects.select_related("makerspace"),
        )

    def perform_update(self, serializer):
        frontend = serializer.save()
        audit.record(
            self.request.user,
            "tenant_frontend.updated",
            makerspace=frontend.makerspace,
            target=frontend,
        )
