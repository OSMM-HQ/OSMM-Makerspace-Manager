from django.apps import AppConfig


class ProcurementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.procurement"
    label = "procurement"

    def ready(self):
        from apps.procurement import signals  # noqa: F401  (registers post_delete receiver)
