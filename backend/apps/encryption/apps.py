from django.apps import AppConfig


class EncryptionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.encryption"

    def ready(self):
        # Registers the enabled-mode wrapping-configuration system check. The
        # check itself no-ops when PII_ENCRYPTION_ENABLED is False, so importing
        # it here never parses key material in a dormant install.
        from apps.encryption import checks  # noqa: F401
