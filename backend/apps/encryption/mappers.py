"""Mapped model save/read boundary for scoped encrypted PII."""

from contextlib import nullcontext

from django.conf import settings
from django.db import connection, models, transaction

from apps.encryption.crypto import decrypt_with_key_loader, encrypt, is_envelope
from apps.encryption.registry import field_for, fields_for, makerspace_id_for
from apps.encryption.services import get_dek, get_or_create_active_dek


class ScopedPiiQuerySet(models.QuerySet):
    def _guard(self, names):
        if settings.PII_ENCRYPTION_ENABLED and any(field_for(self.model, name) for name in names):
            raise RuntimeError("Mapped PII fields require model.save().")

    def update(self, **kwargs):
        self._guard(kwargs)
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        self._guard(fields)
        return super().bulk_update(objs, fields, **kwargs)

    def bulk_create(self, objs, **kwargs):
        if settings.PII_ENCRYPTION_ENABLED and fields_for(self.model):
            raise RuntimeError("Mapped PII models require model.save().")
        return super().bulk_create(objs, **kwargs)


class ScopedPiiManager(models.Manager.from_queryset(ScopedPiiQuerySet)):
    pass


class ScopedPiiModelMixin(models.Model):
    """Keeps DB envelopes in ``__dict__`` and exposes verified plaintext attributes."""

    objects = ScopedPiiManager()

    class Meta:
        abstract = True

    def __getattribute__(self, name):
        value = super().__getattribute__(name)
        if name.startswith("_") or self.__dict__.get("_pii_writing") or not settings.PII_ENCRYPTION_ENABLED:
            return value
        field = field_for(self, name)
        if field is None or value in ("", None):
            return value
        plain = self.__dict__.setdefault("_pii_plain_values", {})
        if name in plain:
            return plain[name]
        if not is_envelope(value):
            if settings.PII_ENCRYPTION_DUAL_READ:
                plain[name] = value
                return value
            from apps.encryption.crypto import LegacyPlaintextRejected
            raise LegacyPlaintextRejected()
        makerspace_id = makerspace_id_for(self, field)
        decrypted = decrypt_with_key_loader(
            value, makerspace_id=makerspace_id, table=self._meta.db_table,
            pk=self.pk, field=name, load_dek=lambda version: get_dek(makerspace_id, version),
        ).decode("utf-8")
        plain[name] = decrypted
        self.__dict__.setdefault("_pii_raw_values", {})[name] = value
        self.__dict__.setdefault("_pii_original_plain_values", {})[name] = decrypted
        return decrypted

    def refresh_from_db(self, *args, **kwargs):
        result = super().refresh_from_db(*args, **kwargs)
        for cache_name in ("_pii_plain_values", "_pii_raw_values", "_pii_original_plain_values"):
            self.__dict__.pop(cache_name, None)
        return result

    def _reserve_pk(self):
        pk_field = self._meta.pk
        with connection.cursor() as cursor:
            cursor.execute("SELECT nextval(pg_get_serial_sequence(%s, %s))", [self._meta.db_table, pk_field.column])
            self.pk = cursor.fetchone()[0]

    def _mapped_values_for_save(self, update_fields, *, is_new=False):
        mapped = fields_for(self)
        deferred = set() if is_new else self.get_deferred_fields()
        return [
            item for item in mapped
            if item.field_name not in deferred
            and (update_fields is None or item.field_name in update_fields)
            and not (item.model_label == "integrations.EmailLog" and self.makerspace_id is None)
        ]

    def save(self, *args, **kwargs):
        if not settings.PII_ENCRYPTION_ENABLED or not fields_for(self):
            return super().save(*args, **kwargs)
        update_fields = kwargs.get("update_fields")
        update_fields = None if update_fields is None else set(update_fields)
        is_new = self._state.adding
        context = transaction.atomic() if is_new else nullcontext()
        with context:
            if is_new and self.pk is None:
                self._reserve_pk()
            encrypted, restore = {}, {}
            for item in self._mapped_values_for_save(update_fields, is_new=is_new):
                raw = self.__dict__.get(item.field_name, "")
                plaintext = self.__dict__.get("_pii_plain_values", {}).get(item.field_name, raw)
                makerspace_id = makerspace_id_for(self, item)
                original = self.__dict__.get("_pii_original_plain_values", {}).get(item.field_name)
                raw_saved = self.__dict__.get("_pii_raw_values", {}).get(item.field_name)
                if raw_saved and plaintext == original:
                    encrypted[item.field_name] = raw_saved
                else:
                    if is_envelope(plaintext):
                        plaintext = decrypt_with_key_loader(plaintext, makerspace_id=makerspace_id, table=self._meta.db_table, pk=self.pk, field=item.field_name, load_dek=lambda version: get_dek(makerspace_id, version)).decode("utf-8")
                    if plaintext not in ("", None):
                        active = get_or_create_active_dek(makerspace_id)
                        encrypted[item.field_name] = encrypt(plaintext.encode("utf-8"), active.dek, key_version=active.key.version, makerspace_id=makerspace_id, table=self._meta.db_table, pk=self.pk, field=item.field_name)
                    else:
                        encrypted[item.field_name] = plaintext
                restore[item.field_name] = plaintext
            self.__dict__.update(encrypted)
            self.__dict__["_pii_writing"] = True
            if is_new:
                kwargs["force_insert"] = True
            try:
                result = super().save(*args, **kwargs)
            finally:
                self.__dict__.pop("_pii_writing", None)
                self.__dict__.update(restore)
            self.__dict__.setdefault("_pii_plain_values", {}).update(restore)
            self.__dict__.setdefault("_pii_raw_values", {}).update(encrypted)
            self.__dict__.setdefault("_pii_original_plain_values", {}).update(restore)
            return result
