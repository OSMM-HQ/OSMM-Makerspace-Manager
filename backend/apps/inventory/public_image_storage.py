import logging
import uuid

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from rest_framework.exceptions import ValidationError

from apps.evidence.storage import StorageUnavailable


logger = logging.getLogger(__name__)


def _s3_client(endpoint_url):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
        config=Config(
            signature_version=settings.AWS_S3_SIGNATURE_VERSION,
            s3={"addressing_style": settings.AWS_S3_ADDRESSING_STYLE},
        ),
    )


def _client():
    return _s3_client(settings.AWS_S3_ENDPOINT_URL)


def _public_client():
    return _s3_client(settings.AWS_S3_PUBLIC_ENDPOINT_URL)


def build_object_key(kind, makerspace_id, ext):
    if kind not in {"items", "makerspace", "printers"}:
        raise ValueError("Invalid public image kind.")
    return f"{kind}/{makerspace_id}/{uuid.uuid4().hex}{ext}"


def staging_key(final_key):
    return f"staging/{final_key}"


def delete_object(object_key):
    if not object_key:
        return
    try:
        _client().delete_object(
            Bucket=settings.PUBLIC_IMAGE_BUCKET,
            Key=object_key,
        )
    except (BotoCoreError, ClientError):
        logger.exception("Failed to delete public image object %s.", object_key)


def put_bytes(object_key, data, content_type):
    try:
        _client().put_object(
            Bucket=settings.PUBLIC_IMAGE_BUCKET,
            Key=object_key,
            Body=data,
            ContentType=content_type,
        )
    except (BotoCoreError, ClientError) as exc:
        raise StorageUnavailable from exc


def copy_object(source_key, dest_key):
    try:
        _client().copy_object(
            Bucket=settings.PUBLIC_IMAGE_BUCKET,
            CopySource={
                "Bucket": settings.PUBLIC_IMAGE_BUCKET,
                "Key": source_key,
            },
            Key=dest_key,
        )
    except (BotoCoreError, ClientError) as exc:
        raise StorageUnavailable from exc


def object_exists(object_key):
    try:
        _client().head_object(
            Bucket=settings.PUBLIC_IMAGE_BUCKET,
            Key=object_key,
        )
    except ClientError as exc:
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        code = exc.response.get("Error", {}).get("Code")
        if status == 404 or code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise StorageUnavailable from exc
    except BotoCoreError as exc:
        raise StorageUnavailable from exc
    return True


def object_size(object_key):
    if not object_exists(object_key):
        return None

    try:
        response = _client().head_object(
            Bucket=settings.PUBLIC_IMAGE_BUCKET,
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


def presigned_upload(object_key, content_type):
    try:
        if settings.STORAGE_PRESIGN_METHOD == "put":
            url = _public_client().generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": settings.PUBLIC_IMAGE_BUCKET,
                    "Key": staging_key(object_key),
                    "ContentType": content_type,
                },
                ExpiresIn=settings.PUBLIC_IMAGE_URL_TTL_SECONDS,
            )
            return {
                "url": url,
                "method": "PUT",
                "headers": {"Content-Type": content_type},
            }
        return _public_client().generate_presigned_post(
            Bucket=settings.PUBLIC_IMAGE_BUCKET,
            Key=object_key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, settings.PUBLIC_IMAGE_MAX_BYTES],
            ],
            ExpiresIn=settings.PUBLIC_IMAGE_URL_TTL_SECONDS,
        )
    except (BotoCoreError, ClientError) as exc:
        raise StorageUnavailable from exc


def finalize_upload(object_key):
    max_bytes = settings.PUBLIC_IMAGE_MAX_BYTES
    if settings.STORAGE_PRESIGN_METHOD != "put":
        return object_size(object_key)

    if object_exists(object_key):
        delete_object(staging_key(object_key))
        return object_size(object_key)

    upload_staging_key = staging_key(object_key)
    size = object_size(upload_staging_key)
    if size is None:
        return None
    if not (1 <= size <= max_bytes):
        return size

    copy_object(upload_staging_key, object_key)
    delete_object(upload_staging_key)
    final_size = object_size(object_key)
    if final_size is None or not (1 <= final_size <= max_bytes):
        delete_object(object_key)
    return final_size


def public_url(object_key):
    if not object_key:
        return ""
    if settings.PUBLIC_IMAGE_BASE_URL:
        return f"{settings.PUBLIC_IMAGE_BASE_URL.rstrip('/')}/{object_key}"
    return (
        f"{settings.AWS_S3_PUBLIC_ENDPOINT_URL.rstrip('/')}/"
        f"{settings.PUBLIC_IMAGE_BUCKET}/{object_key}"
    )


def ext_for(content_type, filename):
    allowed_exts = settings.PUBLIC_IMAGE_ALLOWED_MIME.get(content_type)
    if not allowed_exts:
        raise ValidationError({"content_type": "Unsupported public image content type."})

    safe_name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    ext = f".{safe_name.rsplit('.', 1)[-1].lower()}" if "." in safe_name else ""
    if ext not in allowed_exts:
        raise ValidationError(
            {"filename": "Filename extension does not match the content type."}
        )
    return ext
