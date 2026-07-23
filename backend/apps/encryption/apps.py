from django.apps import AppConfig


class EncryptionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.encryption"

    def ready(self):
        # Registers the enabled-mode wrapping-configuration system check. The
        # check itself no-ops when PII_ENCRYPTION_ENABLED is False, so importing
        # it here never parses key material in a dormant install.
        from apps.encryption import checks  # noqa: F401
        from apps.encryption import signals  # noqa: F401
        # Celery workers do not use the HTTP readiness view.  The signal keeps an
        # enabled worker from accepting generation-bound tasks before its DB/key
        # preflight passes; disabled installs still do no key parsing or DB work.
        try:
            from celery.signals import worker_process_init
        except ImportError:
            return

        @worker_process_init.connect(weak=False)
        def _pii_worker_readiness(**kwargs):
            from django.conf import settings
            if settings.PII_ENCRYPTION_ENABLED:
                from apps.encryption.readiness import assert_ready
                assert_ready()
