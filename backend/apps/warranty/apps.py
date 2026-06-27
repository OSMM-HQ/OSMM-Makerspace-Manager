from django.apps import AppConfig


class WarrantyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.warranty"

    def ready(self):
        from apps.warranty import signals  # noqa: F401  (registers post_delete receiver)
