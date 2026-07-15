from django.apps import AppConfig
from django.db.models.signals import post_delete, post_save


class MakerspacesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.makerspaces"

    def ready(self):
        from apps.makerspaces.cors import register_signal
        from apps.makerspaces.hosting import invalidate
        from apps.makerspaces.models import Makerspace

        register_signal()

        def invalidate_hosting_cache(**kwargs):
            invalidate()

        post_save.connect(
            invalidate_hosting_cache,
            sender=Makerspace,
            dispatch_uid="makerspaces.invalidate_hosting_cache_on_save",
            weak=False,
        )
        post_delete.connect(
            invalidate_hosting_cache,
            sender=Makerspace,
            dispatch_uid="makerspaces.invalidate_hosting_cache_on_delete",
            weak=False,
        )
