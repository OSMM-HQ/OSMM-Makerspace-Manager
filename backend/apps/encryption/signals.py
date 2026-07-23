"""Deletion has no generic FK: remove candidate rows explicitly and narrowly."""

from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.encryption.models import PiiBlindIndex
from apps.encryption.registry import fields_for, makerspace_id_for


@receiver(post_delete)
def remove_deleted_source_indexes(sender, instance, **kwargs):
    fields = [field for field in fields_for(instance) if field.index_kind in {"bloom", "bloom_exact"}]
    if not fields:
        return
    # Post-delete relation traversal may be unavailable for indirect tenant paths;
    # indexes are unique by object/model/field, so the registry-controlled shape is
    # enough and avoids an unsafe broad cleanup.
    PiiBlindIndex.objects.filter(
        model_label=instance._meta.label,
        object_id=instance.pk,
        field_name__in=[field.field_name for field in fields],
    ).delete()
