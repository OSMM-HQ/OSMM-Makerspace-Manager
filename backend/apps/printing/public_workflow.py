from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit
from apps.makerspaces import limits
from apps.printing.emails import notify_print_status
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
from apps.machines.printing_cutover import kernel_is_authoritative


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


def submit_public_print_request(makerspace, data, member):
    if kernel_is_authoritative(makerspace):
        # Compatibility URL, kernel write.  The legacy bucket is resolved by its
        # provenance key and is never created or updated after B4.
        from apps.machines.models import ServiceQueue
        from apps.machines.service_workflow import submit
        legacy_bucket = _resolve_public_bucket(makerspace, data.get("bucket_id"))
        queue = ServiceQueue.objects.filter(legacy_print_bucket_id=legacy_bucket.pk, makerspace=makerspace).first()
        if queue is None:
            raise ValidationError({"bucket_id": "This printing queue has not been reconciled."})
        spool = FilamentSpool.objects.filter(pk=data.get("filament_spool_id"), makerspace=makerspace).first() if data.get("filament_spool_id") else None
        payload = {
            "requested_material": data.get("material") or getattr(spool, "material", ""),
            "requested_color": data.get("color") or getattr(spool, "color", ""),
            "quantity": data.get("quantity", 1), "project_brief": data.get("project_brief", ""),
            **({"requested_consumable_pool": spool.id} if spool else {}),
        }
        return submit(queue, member, requester_name=(member.display_name or ""), contact_email=(member.email or ""),
                      contact_phone=(member.phone or ""), title=data["title"], description=data.get("description", ""),
                      source_link=data.get("source_link", ""), actor=member, member=member, capability_payload=payload)
    with transaction.atomic():
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

        # The model column is non-null (default 0); never pass None into it.
        requested_grams = data.get("estimated_filament_grams")
        if requested_grams is None:
            requested_grams = Decimal("0.00")

        limits.check_quota(makerspace, "print", adding=1)
        request = PrintRequest.objects.create(
            bucket=bucket,
            requester=member,
            requester_name=(member.display_name or "").strip(),
            title=data["title"],
            description=data.get("description", ""),
            project_brief=data.get("project_brief", ""),
            preferred_settings=data.get("preferred_settings", ""),
            material=material,
            color=color,
            requested_filament_spool=spool,
            estimated_filament_grams=requested_grams,
            quantity=data.get("quantity", 1),
            source_link=data.get("source_link", ""),
            contact_email=(member.email or "").strip(),
            contact_phone=(member.phone or "").strip(),
            status=PrintRequest.Status.PENDING,
        )

        file_ids = data.get("file_ids") or []
        if file_ids:
            locked = list(
                PrintRequestFile.objects.select_for_update().filter(
                    id__in=file_ids,
                    owner=member,
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
                limits.add_storage(makerspace, size)
                if upload.kind == PrintRequestFile.Kind.STL:
                    try:
                        validate_print_model_object(
                            upload.object_key,
                            upload.original_filename,
                            upload.content_type,
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

        audit.record(member, "print.submitted", makerspace=makerspace, target=request)
        notify_print_status(request, "submitted")
        return request
