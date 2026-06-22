from django.contrib import admin
from django.utils.html import format_html, format_html_join
from unfold.admin import ModelAdmin

from apps.printing.admin_request_actions import PrintRequestWorkflowActions
from apps.printing.models import PrintRequest
from apps.printing.storage import print_get_url
from config.admin_access import SuperuserOnlyModelAdmin


@admin.register(PrintRequest)
class PrintRequestAdmin(PrintRequestWorkflowActions, SuperuserOnlyModelAdmin, ModelAdmin):
    actions = [
        "accept_selected",
        "reject_selected",
        "complete_selected",
        "fail_selected",
        "start_selected",
        "collect_selected",
        "reprint_selected",
    ]
    list_display = ("status", "bucket", "printer", "requester", "created_at")
    list_filter = ("status", "bucket__makerspace", "bucket", "printer")
    search_fields = (
        "title", "description", "requester__username", "requester__email", "bucket__name"
    )
    readonly_fields = (
        "status", "reason", "handled_by", "printer", "filament_spool",
        "requested_filament_spool", "requester_name",
        "estimated_minutes", "estimated_filament_grams", "created_at", "accepted_at",
        "filament_grams_reserved", "filament_grams_used", "started_at",
        "completed_at", "updated_at", "files_preview",
    )
    fields = (
        "bucket", "requester", "requester_name", "title", "description", "material",
        "color", "quantity", "source_link", "model_file", "preferred_settings",
        "estimate_screenshot", "preview_screenshot", "status", "reason", "handled_by",
        "printer", "filament_spool", "requested_filament_spool", "estimated_minutes",
        "estimated_filament_grams", "filament_grams_reserved",
        "filament_grams_used", "created_at", "accepted_at", "started_at",
        "completed_at", "updated_at", "files_preview",
    )

    def files_preview(self, obj):
        if not obj or not obj.pk:
            return "(save first)"

        # Reprint clones own no PrintRequestFile rows; fall back to the original
        # request's files (mirrors PrintRequestSerializer.get_files) so superusers can
        # still download the model/preview when viewing a reprint.
        files = list(obj.files.all())
        if not files and obj.reprint_of_id:
            files = list(obj.reprint_of.files.all())

        rows = []
        for f in files:
            label = f"{f.kind} #{f.id} ({f.size_bytes} bytes)"
            if (f.content_type or "").startswith("image/"):
                try:
                    url = print_get_url(f.object_key, content_type=f.content_type)
                except Exception:
                    url = ""
                if not url:
                    rows.append(format_html("<div>{} unavailable</div>", label))
                    continue
                rows.append(
                    format_html(
                        '<div><a href="{}" target="_blank" rel="noopener">'
                        '<img src="{}" style="max-height:160px;border:1px solid #ccc"/></a> {}</div>',
                        url,
                        url,
                        label,
                    )
                )
            else:
                try:
                    url = print_get_url(
                        f.object_key,
                        filename=f.original_filename,
                        content_type=f.content_type,
                        as_attachment=True,
                        kind=f.kind,
                    )
                except Exception:
                    url = ""
                if not url:
                    rows.append(format_html("<div>{} unavailable</div>", label))
                    continue
                rows.append(
                    format_html(
                        '<div><a href="{}" target="_blank" rel="noopener">Download {}</a></div>',
                        url,
                        label,
                    )
                )
        if not rows:
            return "(no files)"
        return format_html_join("", "{}", ((r,) for r in rows))

    files_preview.short_description = "Uploaded files"
