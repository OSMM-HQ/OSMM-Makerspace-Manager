"""Small model fields with per-instance insert behaviour."""

from django.db import models


class PreservableCreatedAtField(models.DateTimeField):
    """Keep an explicit historical timestamp on one opted-in INSERT.

    ``auto_now_add`` normally replaces values supplied by an importer.  The
    opt-in flag lives on the model instance, rather than mutating the shared
    Field object, so concurrent inserts cannot leak timestamp behaviour into
    one another.
    """

    def pre_save(self, model_instance, add):
        if (
            add
            and getattr(model_instance, "_preserve_created_at", False)
            and getattr(model_instance, self.attname) is not None
        ):
            return getattr(model_instance, self.attname)
        return super().pre_save(model_instance, add)
