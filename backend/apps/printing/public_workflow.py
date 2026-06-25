from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.audit import services as audit
from apps.hardware_requests.workflow_utils import get_or_create_requester
from apps.printing.emails import queue_print_email, queue_staff_print_email
from apps.printing.models import (
    FilamentSpool,
    PrintBucket,
    PrintRequest,
    PrintRequestFile,
)
from apps.printing.storage import (
    print_finalize_upload,
    print_object_size,
    validate_print_model_object,
)


def _resolve_public_bucket(makerspace, bucket_id):
    # Distinguish an omitted/null bucket (use the default) from an explicit invalid id like 0
    # (which can't be a real PK) - the latter must still raise the validation error, not fall
    # through to the default "Public Requests" queue.
    if bucket_id is not None:
        bucket = PrintBucket.objects.filter(
            pk=bucket_id,
            makerspace=makerspace,
            is_active=True,
        ).first()
        if bucket is None:
            raise ValidationError({"bucket_id": "Invalid or inactive bucket."})
        return bucket

    try:
        with transaction.atomic():
            bucket, _ = PrintBucket.objects.get_or_create(
                makerspace=makerspace,
                name="Public Requests",
                defaults={"is_active": True},
            )
    except IntegrityError:
        bucket = PrintBucket.objects.get(makerspace=makerspace, name="Public Requests")

    if not bucket.is_active:
        bucket.is_active = True
        bucket.save(update_fields=["is_active"])
    return bucket


def submit_public_print_request(makerspace, data, result):
    with transaction.atomic():
        requester = get_or_create_requester(result.external_id)
        if requester.access_status != User.AccessStatus.ACTIVE:
            raise PermissionDenied("Requester is not active.")

        bucket = _resolve_public_bucket(makerspace, data.get("bucket_id"))
        spool = None
        spool_id = data.get("filament_spool_id")
        if spool_id is not None:
            spool = FilamentSpool.objects.filter(
                pk=spool_id,
                makerspace=makerspace,
                is_active=True,
            ).first()
            if spool is None:
                raise ValidationError(
                    {"filament_spool_id": "Invalid or inactive spool."}
                )

        material = data.get("material", "")
        color = data.get("color", "")
        if spool is not None:
            material = material or spool.material
            color = color or spool.color

        request = PrintRequest.objects.create(
            bucket=bucket,
            requester=requester,
            requester_name=data.get("requester_name", "").strip(),
            title=data["title"],
            description=data.get("description", ""),
            project_brief=data.get("project_brief", ""),
            preferred_settings=data.get("preferred_settings", ""),
            material=material,
            color=color,
            requested_filament_spool=spool,
            quantity=data.get("quantity", 1),
            source_link=data.get("source_link", ""),
            contact_email=data.get("contact_email", "").strip(),
            contact_phone=data.get("contact_phone", "").strip(),
            status=PrintRequest.Status.PENDING,
        )

        file_ids = data.get("file_ids") or []
        if file_ids:
            locked = list(
                PrintRequestFile.objects.select_for_update().filter(
                    id__in=file_ids,
                    owner_checkin_user_id=result.external_id,
                    makerspace=makerspace,
                    attached_at__isnull=True,
                )
            )
            if len(locked) != len(set(file_ids)):
                raise ValidationError(
                    {
                        "file_ids": (
                            "One or more uploads are invalid, already used, or not yours."
                        )
                    }
                )

            now = timezone.now()
            for upload in locked:
                # PUT mode promotes staging->final (write-once); POST mode heads the
                # final key directly. Both then range-check (printing always has).
                if settings.STORAGE_PRESIGN_METHOD == "put":
                    size = print_finalize_upload(
                        upload.object_key, settings.PRINT_UPLOAD_MAX_BYTES
                    )
                else:
                    size = print_object_size(upload.object_key)
                if size is None:
                    raise ValidationError(
                        {"file_ids": "An uploaded file was not found in storage."}
                    )
                if not (1 <= size <= settings.PRINT_UPLOAD_MAX_BYTES):
                    raise ValidationError(
                        {"file_ids": "An uploaded file exceeds the size limit."}
                    )
                if upload.kind == PrintRequestFile.Kind.STL:
                    try:
                        validate_print_model_object(
                            upload.object_key,
                            upload.original_filename,
                            size,
                        )
                    except ValueError as exc:
                        raise ValidationError(
                            {"file_ids": "An uploaded model file is invalid."}
                        ) from exc
                upload.print_request = request
                upload.attached_at = now
                upload.size_bytes = size
                upload.save(
                    update_fields=["print_request", "attached_at", "size_bytes"]
                )

        audit.record(requester, "print.submitted", makerspace=makerspace, target=request)
        # Send the acknowledgement only after the row + file attachments commit, so a
        # rolled-back submit never emails a "received" confirmation.
        queue_print_email("submitted", request.pk)
        queue_staff_print_email("submitted", request.pk)
        return request
