from pathlib import PurePosixPath

from apps.evidence.image_validation import image_mime_from_bytes


ALLOWED_EXTENSIONS_BY_MIME = {
    "application/pdf": {"pdf"},
    "image/jpeg": {"jpg", "jpeg"},
    "image/png": {"png"},
    "image/webp": {"webp"},
    "application/octet-stream": {
        "stl", "3mf", "step", "stp", "obj", "amf", "ply", "gcode",
        "gco", "iges", "igs", "dxf",
    },
    "model/stl": {"stl"},
    "application/sla": {"stl"},
    "application/vnd.ms-pki.stl": {"stl"},
    "text/plain": {
        "stl", "step", "stp", "obj", "amf", "ply", "gcode", "gco",
        "iges", "igs", "dxf",
    },
    "model/3mf": {"3mf"},
    "application/vnd.ms-package.3dmanufacturing-3dmodel+xml": {"3mf"},
    "application/vnd.ms-3mfdocument": {"3mf"},
    "application/step": {"step", "stp"},
    "model/step": {"step", "stp"},
    "model/obj": {"obj"},
    "application/xml": {"amf"},
    "text/xml": {"amf"},
    "application/x-amf": {"amf"},
    "model/amf": {"amf"},
    "application/x-ply": {"ply"},
    "model/ply": {"ply"},
    "text/x.gcode": {"gcode", "gco"},
    "application/x-gcode": {"gcode", "gco"},
    "application/iges": {"iges", "igs"},
    "model/iges": {"iges", "igs"},
    "image/vnd.dxf": {"dxf"},
    "application/dxf": {"dxf"},
    "application/x-dxf": {"dxf"},
}

STRICT_MIME_BY_EXTENSION = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}

ZIP_LOCAL_FILE_MAGIC = b"PK\x03\x04"
SIGNATURE_SNIFF_BYTES = 8192


def extension_from_name(filename_or_key):
    name = str(filename_or_key or "").replace(chr(92), "/").rsplit("/", 1)[-1]
    return PurePosixPath(name).suffix.lower().lstrip(".")


def allowed_pair(ext, content_type, allowed_exts, allowed_mimes):
    normalized_ext = str(ext or "").lower().lstrip(".")
    normalized_mime = str(content_type or "").lower().strip()
    configured_exts = {str(value).lower().lstrip(".") for value in allowed_exts}
    configured_mimes = {str(value).lower().strip() for value in allowed_mimes}
    return (
        normalized_ext in configured_exts
        and normalized_mime in configured_mimes
        and normalized_mime in ALLOWED_EXTENSIONS_BY_MIME
        and normalized_ext in ALLOWED_EXTENSIONS_BY_MIME[normalized_mime]
    )


def sniff_pdf_or_image(data):
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return image_mime_from_bytes(data)


def has_required_signature(ext, data):
    normalized_ext = str(ext or "").lower().lstrip(".")
    prefix = data[:SIGNATURE_SNIFF_BYTES]
    if normalized_ext == "3mf":
        return prefix.startswith(ZIP_LOCAL_FILE_MAGIC)
    if normalized_ext in {"step", "stp"}:
        return b"ISO-10303" in prefix.upper()
    return True
