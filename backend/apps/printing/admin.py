from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.accounts import rbac
from apps.accounts.models import User
from apps.makerspaces.models import Makerspace
from apps.printing.models import FilamentSpool, PrintBucket, PrintPrinter, PrintRequest

MANAGER_ROLES = (User.Role.SUPERADMIN, User.Role.SPACE_MANAGER)


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
            and (
                u.is_superuser
                or u.role in MANAGER_ROLES
                or bool(rbac.makerspaces_for_action(u, rbac.Action.MANAGE_PRINTING))
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
    list_display = ("status", "bucket", "printer", "requester", "created_at")
    list_filter = ("status", "bucket__makerspace", "bucket", "printer")
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
        "printer",
        "filament_spool",
        "estimated_minutes",
        "estimated_filament_grams",
        "created_at",
        "accepted_at",
        "started_at",
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
        "model_file",
        "preferred_settings",
        "estimate_screenshot",
        "preview_screenshot",
        "status",
        "reason",
        "handled_by",
        "printer",
        "filament_spool",
        "estimated_minutes",
        "estimated_filament_grams",
        "created_at",
        "accepted_at",
        "started_at",
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
        if db_field.name == "printer" and not _is_superadmin(request.user):
            scope = rbac.makerspaces_for_action(
                request.user, rbac.Action.MANAGE_PRINTING
            )
            ids = [] if scope is rbac.ALL else scope
            kwargs["queryset"] = PrintPrinter.objects.filter(makerspace_id__in=ids)
        if db_field.name == "filament_spool" and not _is_superadmin(request.user):
            scope = rbac.makerspaces_for_action(
                request.user, rbac.Action.MANAGE_PRINTING
            )
            ids = [] if scope is rbac.ALL else scope
            kwargs["queryset"] = FilamentSpool.objects.filter(makerspace_id__in=ids)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(PrintPrinter)
class PrintPrinterAdmin(PrintingAdminMixin, ModelAdmin):
    list_display = ("name", "makerspace", "status", "is_active", "updated_at")
    list_filter = ("status", "is_active", "makerspace")
    search_fields = ("name", "model", "notes", "makerspace__name", "makerspace__slug")
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "makerspace",
        "name",
        "model",
        "status",
        "notes",
        "is_active",
        "created_at",
        "updated_at",
    )

    def get_queryset(self, request):
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


@admin.register(FilamentSpool)
class FilamentSpoolAdmin(PrintingAdminMixin, ModelAdmin):
    list_display = (
        "material",
        "color",
        "printer",
        "makerspace",
        "remaining_weight_grams",
        "is_active",
    )
    list_filter = ("material", "is_active", "makerspace", "printer")
    search_fields = (
        "material",
        "color",
        "brand",
        "lot_code",
        "printer__name",
        "makerspace__name",
    )
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "makerspace",
        "printer",
        "material",
        "color",
        "brand",
        "lot_code",
        "initial_weight_grams",
        "remaining_weight_grams",
        "is_active",
        "opened_at",
        "created_at",
        "updated_at",
    )

    def get_queryset(self, request):
        return rbac.scope_by_action(
            request.user,
            rbac.Action.MANAGE_PRINTING,
            super().get_queryset(request).select_related("printer", "makerspace"),
            "makerspace_id",
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not _is_superadmin(request.user):
            scope = rbac.makerspaces_for_action(
                request.user, rbac.Action.MANAGE_PRINTING
            )
            ids = [] if scope is rbac.ALL else scope
            if db_field.name == "makerspace":
                kwargs["queryset"] = Makerspace.objects.filter(id__in=ids)
                kwargs["required"] = True
            if db_field.name == "printer":
                kwargs["queryset"] = PrintPrinter.objects.filter(makerspace_id__in=ids)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
