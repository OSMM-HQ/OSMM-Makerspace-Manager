from django.db import transaction
from rest_framework import serializers

from apps.bookings.models import BookableSpace


def _locked_space(space_id):
    return (
        BookableSpace.objects.select_for_update()
        .select_related('makerspace')
        .get(pk=space_id)
    )


def validate_space_image_key(space, object_key, storage):
    if not storage.is_owned_object_key(space, object_key):
        raise serializers.ValidationError(
            {'object_key': 'Image object key is outside this space.'}
        )
    if not storage.has_allowed_extension(object_key):
        raise serializers.ValidationError(
            {'object_key': 'Image object key has an unsupported extension.'}
        )


def _active_space(space_id):
    locked = _locked_space(space_id)
    if not locked.is_active:
        raise serializers.ValidationError(
            {'space': 'Inactive spaces cannot have images changed.'}
        )
    return locked


@transaction.atomic
def cleanup_unattached_space_image(space, *, object_key, storage):
    _locked_space(space.pk)
    if not BookableSpace.objects.filter(image_key=object_key).exists():
        storage.delete_object(object_key)
    staging_key = storage.staging_key(object_key)
    if staging_key != object_key:
        storage.delete_object(staging_key)


def set_space_image(
    space,
    *,
    actor,
    object_key,
    size_bytes,
    audit,
    limits,
    storage,
):
    locked = _active_space(space.pk)
    validate_space_image_key(locked, object_key, storage)
    if storage.public_image_key_in_use(locked.makerspace_id, object_key):
        raise serializers.ValidationError(
            {'object_key': 'This image is already in use.'}
        )
    old_key = locked.image_key
    old_size = storage.object_size(old_key) if old_key else None
    if old_key and old_size is None:
        raise serializers.ValidationError(
            {'image': 'The existing image was not found in storage.'}
        )
    limits.add_storage(locked.makerspace, size_bytes)
    if old_key:
        limits.free_storage(locked.makerspace, old_size)
    locked.image_key = object_key
    locked.save(update_fields=['image_key', 'updated_at'])
    audit.record(
        actor,
        'booking.space_image_updated',
        makerspace=locked.makerspace,
        target=locked,
        meta={'replaced_image': bool(old_key)},
    )
    if old_key:
        transaction.on_commit(lambda key=old_key: storage.delete_object(key))
    locked.refresh_from_db()
    return locked


def remove_space_image(space, *, actor, audit, limits, storage):
    locked = _active_space(space.pk)
    if not locked.image_key:
        raise serializers.ValidationError({'image': 'This space has no image.'})
    validate_space_image_key(locked, locked.image_key, storage)
    old_key = locked.image_key
    old_size = storage.object_size(old_key)
    if old_size is None:
        raise serializers.ValidationError(
            {'image': 'The existing image was not found in storage.'}
        )
    limits.free_storage(locked.makerspace, old_size)
    locked.image_key = None
    locked.save(update_fields=['image_key', 'updated_at'])
    audit.record(
        actor,
        'booking.space_image_removed',
        makerspace=locked.makerspace,
        target=locked,
        meta={},
    )
    transaction.on_commit(lambda key=old_key: storage.delete_object(key))
    locked.refresh_from_db()
    return locked
