from decimal import Decimal
import json

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


def _kernel_preferred_settings(value):
    """Translate the legacy text field to the printer pack's JSON object."""
    if not value:
        return None
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({
            "preferred_settings": "Printer preferred settings must be a JSON object after cutover.",
        }) from exc
    if not isinstance(parsed, dict):
        raise ValidationError({"preferred_settings": "Printer preferred settings must be a JSON object."})
    return parsed


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


def resolve_kernel_public_queue(makerspace, bucket_id):
    """Resolve the kernel queue without creating or modifying a legacy bucket."""
    from apps.machines.models import ServiceQueue

    queues = ServiceQueue.objects.filter(
        makerspace=makerspace,
        is_active=True,
        legacy_print_bucket_id__isnull=False,
        machine_type__slug="3d_printer",
    )
    if bucket_id is not None:
        queue = queues.filter(legacy_print_bucket_id=bucket_id).first()
        if queue is None:
            raise ValidationError({"bucket_id": "Invalid or inactive bucket."})
        return queue
    queue = queues.filter(name="Public Requests").first()
    if queue is None:
        raise ValidationError({"bucket_id": "Select an active reconciled printing queue."})
    return queue


def submit_public_print_request(makerspace, data, member):
    if kernel_is_authoritative(makerspace):
        # Compatibility URL, kernel write.  No legacy queue is created or
        # changed after B4; queued uploads are staged directly against the
        # reconciled ServiceQueue and attached after submit.
        from apps.machines.models import MachineConsumablePool, ServiceRequestFile
        from apps.machines.service_workflow import submit
        from apps.machines.service_storage import finalize_file

        queue = resolve_kernel_public_queue(makerspace, data.get("bucket_id"))
        spool = None
        spool_id = data.get("filament_spool_id")
        if spool_id is not None:
            spool = FilamentSpool.objects.filter(
                pk=spool_id, makerspace=makerspace, is_active=True,
            ).first()
            if spool is None:
                raise ValidationError({"filament_spool_id": "Invalid or inactive spool."})
            pool = MachineConsumablePool.objects.filter(
                legacy_filament_spool_id=spool.pk, makerspace=makerspace, is_active=True,
            ).first()
            if pool is None:
                raise ValidationError({"filament_spool_id": "This spool has not been reconciled."})
        else:
            pool = None
        config = queue.machine_type.capability_config
        material = data.get("material") or getattr(spool, "material", "")
        color = data.get("color") or getattr(spool, "color", "")
        no_filament_preference = spool is None and not material and not color
        # The kernel requires concrete, type-valid values.  The default is a
        # representation of an omitted legacy preference, not a forced spool:
        # ``no_filament_preference`` tells start validation to accept any
        # compatible pool selected by staff.
        material = material or config["accepted_materials"][0]
        color = color or config["accepted_colours"][0]
        estimated_grams = data.get("estimated_filament_grams")
        preferred_settings = _kernel_preferred_settings(data.get("preferred_settings", ""))
        payload = {
            "requested_material": material,
            "requested_color": color,
            "quantity": data.get("quantity", 1), "project_brief": data.get("project_brief", ""),
            **({"no_filament_preference": True} if no_filament_preference else {}),
            **({"estimated_grams": str(estimated_grams)} if estimated_grams is not None and estimated_grams > 0 else {}),
            **({"requested_consumable_pool": pool.id} if pool else {}),
            **({"preferred_settings": preferred_settings} if preferred_settings is not None else {}),
        }
        with transaction.atomic():
            # The compatibility URL retains the printing product's monthly
            # quota in addition to the kernel's general service-request
            # limits.  Those limits have different scopes and periods.
            limits.check_quota(makerspace, "print", adding=1)
            request = submit(queue, member, requester_name=(member.display_name or ""), contact_email=(member.email or ""),
                             contact_phone=(member.phone or ""), title=data["title"], description=data.get("description", ""),
                             source_link=data.get("source_link", ""), actor=member, member=member, capability_payload=payload)
            file_ids = data.get("file_ids") or []
            if file_ids:
                files = list(ServiceRequestFile.objects.select_for_update().filter(
                    id__in=file_ids, makerspace=makerspace, queue=queue,
                    owner_user_id=member.pk, service_request__isnull=True,
                    attached_at__isnull=True,
                ))
                if len(files) != len(set(file_ids)):
                    raise ValidationError({"file_ids": "One or more uploads are invalid, already used, or not yours."})
                for file in files:
                    finalize_file(request, file_id=file.pk, actor=member)
            return request
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
