import logging
import uuid

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings


logger = logging.getLogger(__name__)


class StorageUnavailable(Exception):
    pass


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


def evidence_object_key(makerspace_id, evidence_type):
    return f"evidence/{makerspace_id}/{evidence_type}/{uuid.uuid4().hex}"


def staging_key(final_key):
    return f"staging/{final_key}"


def delete_object(object_key):
    try:
        _client().delete_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=object_key,
        )
    except (BotoCoreError, ClientError):
        logger.exception("Failed to delete storage object %s.", object_key)


def copy_object(source_key, dest_key):
    try:
        _client().copy_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            CopySource={
                "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                "Key": source_key,
            },
            Key=dest_key,
        )
    except (BotoCoreError, ClientError) as exc:
        raise StorageUnavailable from exc


def finalize_upload(object_key, max_bytes):
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
    # Re-validate the ACTUAL finalized object. The staging key stays client-writable
    # until its presigned PUT URL expires, so a racing oversized PUT between the size
    # HEAD above and this copy could promote an oversized object while the small size
    # was recorded (Codex Stage-4 P2 TOCTOU). The final key is never client-writable,
    # so its post-copy size is authoritative; reject + delete it if it drifted.
    final_size = object_size(object_key)
    if final_size is None or not (1 <= final_size <= max_bytes):
        delete_object(object_key)
    return final_size


def presigned_upload(object_key, content_type):
    try:
        if settings.STORAGE_PRESIGN_METHOD == "put":
            url = _public_client().generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                    "Key": staging_key(object_key),
                    "ContentType": content_type,
                },
                ExpiresIn=settings.EVIDENCE_URL_TTL_SECONDS,
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
                ["content-length-range", 1, settings.EVIDENCE_MAX_BYTES],
            ],
            ExpiresIn=settings.EVIDENCE_URL_TTL_SECONDS,
        )
    except (BotoCoreError, ClientError) as exc:
        raise StorageUnavailable from exc


def presigned_get_url(object_key):
    try:
        return _public_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": object_key},
            ExpiresIn=settings.EVIDENCE_URL_TTL_SECONDS,
        )
    except (BotoCoreError, ClientError) as exc:
        raise StorageUnavailable from exc


def object_exists(object_key):
    try:
        _client().head_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
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
