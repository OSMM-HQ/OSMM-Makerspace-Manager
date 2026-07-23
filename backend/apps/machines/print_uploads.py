"""3D-printer upload declaration validation owned by the machine kernel."""

from django.conf import settings

from apps.maker_file_formats import allowed_pair, extension_from_name


SCREENSHOT_MIME_BY_EXT = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "webp": "image/webp", "pdf": "application/pdf",
}


def validate_print_upload(kind, filename, content_type):
    content_type = content_type or "application/octet-stream"
    extension = extension_from_name(filename)
    if kind not in {"stl", "screenshot"}:
        raise ValueError("Invalid print upload kind.")
    if kind == "stl":
        if not allowed_pair(extension, content_type, settings.PRINT_ALLOWED_MODEL_EXT, settings.PRINT_ALLOWED_MODEL_MIME):
            raise ValueError("Unsupported model extension or content type.")
        return content_type
    if extension not in settings.PRINT_ALLOWED_SCREENSHOT_EXT:
        raise ValueError("Unsupported screenshot file extension.")
    if content_type not in settings.PRINT_ALLOWED_SCREENSHOT_MIME:
        raise ValueError("Unsupported screenshot file content type.")
    if SCREENSHOT_MIME_BY_EXT.get(extension) != content_type:
        raise ValueError("Screenshot extension and content type do not match.")
    return content_type
