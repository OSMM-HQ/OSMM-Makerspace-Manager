from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core.exceptions import ValidationError
from django.template.response import TemplateResponse
from unfold.admin import ModelAdmin, TabularInline

from apps.makerspaces.models import Makerspace, MakerspaceMembership, TenantFrontend
from config.admin_access import SuperuserOnlyModelAdmin


class ArchivedFilter(admin.SimpleListFilter):
    title = "archived"
    parameter_name = "archived"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Yes"),
            ("no", "No"),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(archived_at__isnull=False)
        if self.value() == "no":
            return queryset.filter(archived_at__isnull=True)
        return queryset


class MakerspaceMembershipInline(TabularInline):
    model = MakerspaceMembership
    fk_name = "makerspace"
    fields = ("user", "role")
    autocomplete_fields = ("user",)
    extra = 0


@admin.register(Makerspace)
class MakerspaceAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    actions = ["archive_makerspaces", "unarchive_makerspaces", "purge_makerspaces"]
    list_display = (
        "name",
        "public_code",
        "slug",
        "location",
        "public_inventory_enabled",
        "archived",
        "updated_at",
    )
    list_filter = ("public_inventory_enabled", ArchivedFilter)
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "public_code", "slug", "location")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "public_code",
                    "slug",
                    "location",
                    "public_inventory_enabled",
                    "default_loan_days",
                )
            },
        ),
    )
    inlines = (MakerspaceMembershipInline,)

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(boolean=True, description="Archived")
    def archived(self, obj):
        return obj.archived_at is not None

    @admin.action(description="Archive selected makerspaces")
    def archive_makerspaces(self, request, queryset):
        from apps.makerspaces import lifecycle

        for makerspace in list(queryset):
            try:
                lifecycle.archive(makerspace, request.user)
            except ValidationError as err:
                self.message_user(
                    request,
                    f"{makerspace.name} ({makerspace.slug}): {str(err)}",
                    level=messages.ERROR,
                )
            else:
                self.message_user(
                    request,
                    f"Archived makerspace {makerspace.name} ({makerspace.slug}).",
                    level=messages.SUCCESS,
                )

    @admin.action(description="Unarchive selected makerspaces")
    def unarchive_makerspaces(self, request, queryset):
        from apps.makerspaces import lifecycle

        for makerspace in list(queryset):
            try:
                lifecycle.unarchive(makerspace, request.user)
            except ValidationError as err:
                self.message_user(
                    request,
                    f"{makerspace.name} ({makerspace.slug}): {str(err)}",
                    level=messages.ERROR,
                )
            else:
                self.message_user(
                    request,
                    f"Unarchived makerspace {makerspace.name} ({makerspace.slug}).",
                    level=messages.SUCCESS,
                )

    @admin.action(description="Purge selected archived makerspaces")
    def purge_makerspaces(self, request, queryset):
        makerspaces = list(queryset)
        if "confirm_purge" not in request.POST:
            context = {
                **self.admin_site.each_context(request),
                "title": "Purge selected makerspaces",
                "queryset": makerspaces,
                "opts": self.model._meta,
                "action_name": "purge_makerspaces",
                "action_checkbox_name": ACTION_CHECKBOX_NAME,
            }
            return TemplateResponse(
                request,
                "admin/makerspaces/purge_confirmation.html",
                context,
            )

        from apps.makerspaces import lifecycle

        for makerspace in makerspaces:
            if request.POST.get(f"slug_{makerspace.pk}", "") != makerspace.slug:
                self.message_user(
                    request,
                    f"{makerspace.name} ({makerspace.slug}): slug confirmation did not match",
                    level=messages.ERROR,
                )
                continue

            name = makerspace.name
            slug = makerspace.slug
            try:
                lifecycle.purge(makerspace, request.user)
            except ValidationError as err:
                self.message_user(
                    request,
                    f"{name} ({slug}): {str(err)}",
                    level=messages.ERROR,
                )
            else:
                self.message_user(
                    request,
                    f"Purged makerspace {name} ({slug}).",
                    level=messages.SUCCESS,
                )
        return None


@admin.register(MakerspaceMembership)
class MakerspaceMembershipAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("user", "makerspace", "role", "created_at")
    list_filter = ("makerspace", "role")
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user", "makerspace")
    readonly_fields = ("created_at",)


@admin.register(TenantFrontend)
class TenantFrontendAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("makerspace", "frontend_type", "hostname", "is_primary", "is_active", "updated_at")
    list_filter = ("makerspace", "frontend_type", "is_primary", "is_active")
    search_fields = ("makerspace__name", "makerspace__slug", "hostname", "token")
    autocomplete_fields = ("makerspace", "created_by")
    readonly_fields = ("token", "created_at", "updated_at")
