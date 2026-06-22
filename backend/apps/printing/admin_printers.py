from django.contrib import admin, messages
from unfold.admin import ModelAdmin

from apps.audit import services as audit
from apps.inventory import public_image_storage
from apps.inventory.admin_image_uploads import PublicImageAdminForm, PublicImageAdminMixin
from apps.printing.models import FilamentSpool, PrintPrinter, PrintRequest
from config.admin_access import SuperuserOnlyModelAdmin


class PrintPrinterAdminForm(PublicImageAdminForm):
    class Meta:
        model = PrintPrinter
        fields = "__all__"


@admin.register(PrintPrinter)
class PrintPrinterAdmin(PublicImageAdminMixin, SuperuserOnlyModelAdmin, ModelAdmin):
    form = PrintPrinterAdminForm
    image_field = "image_key"
    image_kind = "printers"
    image_attach_action = "printing.printer_image_attached"
    image_clear_action = "printing.printer_image_cleared"
    actions = ["delete_safely"]
    list_display = ("name", "makerspace", "status", "is_active", "updated_at")
    list_filter = ("status", "is_active", "makerspace")
    search_fields = ("name", "model", "notes", "makerspace__name", "makerspace__slug")
    readonly_fields = ("image_preview", "created_at", "updated_at")
    fields = (
        "makerspace",
        "name",
        "model",
        "status",
        "notes",
        "image_preview",
        "image_upload",
        "clear_image",
        "is_active",
        "created_at",
        "updated_at",
    )

    def has_delete_permission(self, request, obj=None):
        # Force deletion through the reference-guarded `delete_safely` action only — disabling
        # the built-in delete removes `delete_selected` + the per-object delete view, so a
        # superuser can't hard-delete a referenced printer and silently SET_NULL history.
        return False

    @admin.action(description="Safely delete selected printers")
    def delete_safely(self, request, queryset):
        success_count = 0
        for printer in queryset:
            if (
                PrintRequest.objects.filter(printer=printer).exists()
                or FilamentSpool.objects.filter(printer=printer).exists()
            ):
                self.message_user(
                    request,
                    (
                        f"{printer.pk}: This printer is linked to print requests or "
                        "spools; deactivate it instead to preserve history."
                    ),
                    level=messages.ERROR,
                )
                continue
            audit.record(
                request.user,
                "printing.printer_deleted",
                makerspace=printer.makerspace,
                target=printer,
            )
            if printer.image_key:
                public_image_storage.delete_object(printer.image_key)
            printer.delete()
            success_count += 1

        if success_count:
            self.message_user(
                request,
                f"Safely deleted {success_count} printer(s).",
                level=messages.SUCCESS,
            )
