from django.apps import AppConfig


class MakerspacesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.makerspaces"

    def ready(self):
        from apps.makerspaces.cors import register_signal

        register_signal()
