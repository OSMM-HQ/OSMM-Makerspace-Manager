from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.accounts import rbac
from apps.accounts.models import User
from apps.makerspaces.models import Makerspace
from apps.printing.models import PrintBucket, PrintRequest

MANAGER_ROLES = (User.Role.SUPERADMIN, User.Role.ADMIN)


def _is_superadmin(user):
    return user.is_superuser or user.role == User.Role.SUPERADMIN


class PrintingAdminMixin:
    def has_module_permission(self, request):
        u = getattr(request, "user", None)
        return bool(
            u
            and u.is_authenticated
            and u.is_active
            and u.access_status == User.AccessStatus.ACTIVE
            and (u.is_superuser or u.role in MANAGER_ROLES)
        )

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)


@admin.register(PrintBucket)
class PrintBucketAdmin(PrintingAdminMixin, ModelAdmin):
    list_display = ("name", "makerspace", "is_active", "updated_at")
    list_filter = ("is_active", "makerspace")
    search_fields = ("name", "description", "makerspace__name", "makerspace__slug")
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "makerspace",
        "name",
        "description",
        "is_active",
        "created_at",
        "updated_at",
    )

    def get_queryset(self, request):
        # Action-aware: only makerspaces where the user's membership grants
        # MANAGE_PRINTING (a global-admin who is merely a guest_admin member of a
        # space must NOT manage that space's buckets — matches rbac.can).
        return rbac.scope_by_action(
            request.user,
            rbac.Action.MANAGE_PRINTING,
            super().get_queryset(request),
            "makerspace_id",
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "makerspace" and not _is_superadmin(request.user):
            scope = rbac.makerspaces_for_action(
                request.user, rbac.Action.MANAGE_PRINTING
            )
            ids = [] if scope is rbac.ALL else scope
            kwargs["queryset"] = Makerspace.objects.filter(id__in=ids)
            kwargs["required"] = True
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(PrintRequest)
class PrintRequestAdmin(PrintingAdminMixin, ModelAdmin):
    list_display = ("status", "bucket", "requester", "created_at")
    list_filter = ("status", "bucket__makerspace", "bucket")
    search_fields = (
        "title",
        "description",
        "requester__username",
        "requester__email",
        "bucket__name",
    )
    readonly_fields = (
        "status",
        "reason",
        "handled_by",
        "created_at",
        "accepted_at",
        "completed_at",
        "updated_at",
    )
    fields = (
        "bucket",
        "requester",
        "title",
        "description",
        "material",
        "color",
        "quantity",
        "source_link",
        "status",
        "reason",
        "handled_by",
        "created_at",
        "accepted_at",
        "completed_at",
        "updated_at",
    )

    def get_queryset(self, request):
        return rbac.scope_by_action(
            request.user,
            rbac.Action.MANAGE_PRINTING,
            super().get_queryset(request).select_related(
                "bucket__makerspace", "requester", "handled_by"
            ),
            "bucket__makerspace_id",
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "bucket" and not _is_superadmin(request.user):
            scope = rbac.makerspaces_for_action(
                request.user, rbac.Action.MANAGE_PRINTING
            )
            ids = [] if scope is rbac.ALL else scope
            kwargs["queryset"] = PrintBucket.objects.filter(makerspace_id__in=ids)
            kwargs["required"] = True
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
