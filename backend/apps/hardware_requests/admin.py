from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from apps.accounts import rbac
from apps.accounts.models import User
from apps.hardware_requests.models import (
    HardwareEmailTemplate,
    HardwareRequest,
    HardwareRequestItem,
)
from apps.makerspaces.models import Makerspace

MANAGER_ROLES = (User.Role.SUPERADMIN, User.Role.SPACE_MANAGER)


class HardwareRequestItemInline(TabularInline):
    model = HardwareRequestItem
    extra = 0
    can_delete = False
    readonly_fields = (
        "product",
        "requested_quantity",
        "accepted_quantity",
        "issued_quantity",
        "returned_quantity",
        "damaged_quantity",
        "missing_quantity",
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(HardwareRequest)
class HardwareRequestAdmin(ModelAdmin):
    list_display = (
        "id",
        "status",
        "makerspace",
        "requester_username",
        "return_due_at",
        "created_at",
    )
    list_filter = ("status", "makerspace")
    search_fields = (
        "requester_username",
        "requested_for",
        "rejection_reason",
        "items__product__name",
    )
    readonly_fields = (
        "makerspace",
        "requester",
        "requester_username",
        "status",
        "requested_for",
        "rejection_reason",
        "accepted_by",
        "accepted_at",
        "assigned_box",
        "issued_by",
        "issued_at",
        "return_due_at",
        "return_reminder_sent_at",
        "closed_by",
        "closed_at",
        "public_token",
        "created_at",
        "updated_at",
    )
    fields = readonly_fields
    inlines = [HardwareRequestItemInline]

    def has_module_permission(self, request):
        user = getattr(request, "user", None)
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.access_status == User.AccessStatus.ACTIVE
            and (
                user.is_superuser
                or user.role in MANAGER_ROLES
                or bool(rbac.makerspaces_for_action(user, rbac.Action.ACCEPT_REQUEST))
            )
        )

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return rbac.scope_by_action(
            request.user,
            rbac.Action.ACCEPT_REQUEST,
            super()
            .get_queryset(request)
            .select_related(
                "makerspace",
                "requester",
                "accepted_by",
                "assigned_box",
                "issued_by",
                "closed_by",
            ),
        )


@admin.register(HardwareEmailTemplate)
class HardwareEmailTemplateAdmin(ModelAdmin):
    list_display = ("makerspace", "key", "subject", "is_active", "updated_at")
    list_filter = ("key", "is_active", "makerspace")
    search_fields = ("subject", "text_body", "html_body", "makerspace__name")
    autocomplete_fields = ("makerspace",)
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "makerspace",
        "key",
        "subject",
        "text_body",
        "html_body",
        "is_active",
        "created_at",
        "updated_at",
    )

    def has_module_permission(self, request):
        user = getattr(request, "user", None)
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.access_status == User.AccessStatus.ACTIVE
            and (
                user.is_superuser
                or user.role in MANAGER_ROLES
                or bool(rbac.makerspaces_for_action(user, rbac.Action.ACCEPT_REQUEST))
            )
        )

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def get_queryset(self, request):
        return rbac.scope_by_action(
            request.user,
            rbac.Action.ACCEPT_REQUEST,
            super().get_queryset(request).select_related("makerspace"),
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "makerspace" and not (
            request.user.is_superuser or request.user.role == User.Role.SUPERADMIN
        ):
            scope = rbac.makerspaces_for_action(
                request.user, rbac.Action.ACCEPT_REQUEST
            )
            ids = [] if scope is rbac.ALL else scope
            kwargs["queryset"] = Makerspace.objects.filter(id__in=ids)
            kwargs["required"] = True
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
