import mimetypes
import uuid

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.utils.http import content_disposition_header

from apps.evidence.storage import (
    _client,
    _public_client,
    StorageUnavailable,
    copy_object,
    delete_object,
    staging_key,
)


PRINT_MODEL_SNIFF_BYTES = 8192

SCREENSHOT_MIME_BY_EXT = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "pdf": "application/pdf",
}


def print_object_key(makerspace_id, kind):
    return f"print/{makerspace_id}/{kind}/{uuid.uuid4().hex}"


def _extension(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def validate_print_upload(kind, filename, content_type):
    content_type = content_type or "application/octet-stream"
    ext = _extension(filename)

    if kind not in {"stl", "screenshot"}:
        raise ValueError("Invalid print upload kind.")

    if kind == "stl":
        if ext not in settings.PRINT_ALLOWED_MODEL_EXT:
            raise ValueError("Unsupported model file extension.")
        if content_type not in settings.PRINT_ALLOWED_MODEL_MIME:
            raise ValueError("Unsupported model file content type.")
        return content_type

    if ext not in settings.PRINT_ALLOWED_SCREENSHOT_EXT:
        raise ValueError("Unsupported screenshot file extension.")
    if content_type not in settings.PRINT_ALLOWED_SCREENSHOT_MIME:
        raise ValueError("Unsupported screenshot file content type.")
    if SCREENSHOT_MIME_BY_EXT.get(ext) != content_type:
        raise ValueError("Screenshot extension and content type do not match.")
    return content_type
def presigned_print_upload(object_key, content_type):
    try:
        if settings.STORAGE_PRESIGN_METHOD == "put":
            # Presigned PUT cannot enforce content-length at upload time; finalize HEADs staging.
            url = _public_client().generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                    "Key": staging_key(object_key),
                    "ContentType": content_type,
                },
                ExpiresIn=settings.PRINT_URL_TTL_SECONDS,
            )
            return {
                "url": url,
                "method": "PUT",
                "headers": {"Content-Type": content_type},
            }
        return _public_client().generate_presigned_post(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=object_key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, settings.PRINT_UPLOAD_MAX_BYTES],
            ],
            ExpiresIn=settings.PRINT_URL_TTL_SECONDS,
        )
    except (BotoCoreError, ClientError) as exc:
        raise StorageUnavailable from exc


# Model content-types map to a concrete extension; STL commonly arrives as
# application/octet-stream (no hint), which is why model kind also has a hard default.
_MODEL_EXT_BY_MIME = {
    "model/stl": ".stl",
    "application/sla": ".stl",
    "application/vnd.ms-pki.stl": ".stl",
    "model/3mf": ".3mf",
    "application/vnd.ms-package.3dmanufacturing-3dmodel+xml": ".3mf",
    "application/step": ".step",
    "model/step": ".step",
}
_SCREENSHOT_EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


def _fallback_extension(content_type, kind):
    content_type = content_type or ""
    ext = _MODEL_EXT_BY_MIME.get(content_type) or _SCREENSHOT_EXT_BY_MIME.get(content_type)
    # Model kind without a precise mime (notably octet-stream, which mimetypes would
    # otherwise guess as .bin) must still download as an openable model file -> .stl.
    if not ext and kind == "stl":
        return ".stl"
    if not ext and content_type:
        ext = mimetypes.guess_extension(content_type) or ""
    return ext


def _download_disposition(filename, content_type, kind=None):
    raw_name = filename or ""
    safe_name = raw_name.replace("\\", "/").rsplit("/", 1)[-1]
    safe_name = "".join(
        char
        for char in safe_name
        if char != '"' and ord(char) >= 0x20 and ord(char) != 0x7F
    )
    if not safe_name:
        safe_name = "download"
    # Guarantee an extension so the OS can open the file. A stored "model.stl" keeps its
    # extension; an empty/extensionless name (the bug: octet-stream STL with no filename
    # produced a plain "download") gets one derived from content-type or kind.
    if "." not in safe_name:
        safe_name = f"{safe_name}{_fallback_extension(content_type, kind)}"
    return content_disposition_header(as_attachment=True, filename=safe_name)


def print_get_url(
    object_key, *, filename=None, content_type=None, as_attachment=False, kind=None
):
    params = {"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": object_key}
    if content_type:
        params["ResponseContentType"] = content_type
    if as_attachment:
        params["ResponseContentDisposition"] = _download_disposition(
            filename,
            content_type,
            kind,
        )
    try:
        return _public_client().generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=settings.PRINT_URL_TTL_SECONDS,
        )
    except (BotoCoreError, ClientError) as exc:
        raise StorageUnavailable from exc


def print_object_size(object_key):
    try:
        response = _client().head_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=object_key,
        )
    except ClientError as exc:
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        code = exc.response.get("Error", {}).get("Code")
        if status == 404 or code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise StorageUnavailable from exc
    except BotoCoreError as exc:
        raise StorageUnavailable from exc

    return int(response["ContentLength"])


def validate_print_model_object(object_key, filename, size_bytes=None):
    ext = _extension(filename)
    if ext not in settings.PRINT_ALLOWED_MODEL_EXT:
        raise ValueError("Unsupported model file extension.")
    data = _print_object_prefix(object_key)
    if ext == "stl" and _looks_like_stl(data, size_bytes):
        return
    if ext == "3mf" and data.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return
    upper = data.upper()
    if ext in {"step", "stp"} and b"ISO-10303" in upper:
        return
    if ext == "obj" and _looks_like_obj(data):
        return
    raise ValueError("Uploaded model file does not match its extension.")


def _print_object_prefix(object_key):
    try:
        response = _client().get_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=object_key,
            Range=f"bytes=0-{PRINT_MODEL_SNIFF_BYTES - 1}",
        )
        return response["Body"].read(PRINT_MODEL_SNIFF_BYTES)
    except (BotoCoreError, ClientError, OSError) as exc:
        raise StorageUnavailable from exc


def _looks_like_stl(data, size_bytes):
    if data.lstrip().lower().startswith(b"solid"):
        return True
    return size_bytes is not None and size_bytes >= 84 and (size_bytes - 84) % 50 == 0


def _looks_like_obj(data):
    if b"\x00" in data:
        return False
    text = data.decode("utf-8", errors="ignore")
    tokens = {"v", "vn", "vt", "f", "o", "g", "mtllib", "usemtl"}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.split(maxsplit=1)[0] in tokens:
            return True
    return False

def print_finalize_upload(object_key, max_bytes):
    if settings.STORAGE_PRESIGN_METHOD != "put":
        return print_object_size(object_key)

    final_size = print_object_size(object_key)
    if final_size is not None:
        delete_object(staging_key(object_key))
        return final_size

    upload_staging_key = staging_key(object_key)
    size = print_object_size(upload_staging_key)
    if size is None:
        return None
    if not (1 <= size <= max_bytes):
        return size

    copy_object(upload_staging_key, object_key)
    delete_object(upload_staging_key)
    # Re-validate the ACTUAL finalized object. The staging key stays client-writable
    # until its presigned PUT URL expires, so a racing oversized PUT between the size
    # HEAD above and this copy could promote an oversized object while the small size
    # was recorded (Codex Stage-4 P2 TOCTOU). The final key is never client-writable,
    # so its post-copy size is authoritative; reject + delete it if it drifted.
    final_size = print_object_size(object_key)
    if final_size is None or not (1 <= final_size <= max_bytes):
        delete_object(object_key)
    return final_size
