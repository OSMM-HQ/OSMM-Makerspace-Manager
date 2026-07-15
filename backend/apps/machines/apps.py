from django.apps import AppConfig


class MachinesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.machines"

    def ready(self):
        from apps.machines import signals  # noqa: F401  (registers post_save receiver)
