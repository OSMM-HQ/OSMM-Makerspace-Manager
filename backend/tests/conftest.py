import pytest
from django.core.cache import cache
from django.db import connection


@pytest.fixture(autouse=True)
def disable_axes_by_default(settings, request):
    settings.AXES_ENABLED = False
    settings.CELERY_TASK_ALWAYS_EAGER = True
    _reset_axes_state(request)
    yield
    settings.AXES_ENABLED = False
    settings.CELERY_TASK_ALWAYS_EAGER = True
    _reset_axes_state(request)


def _reset_axes_state(request):
    cache.clear()

    try:
        from axes.handlers.proxy import AxesProxyHandler
        from axes.utils import reset
    except Exception:
        return

    AxesProxyHandler.implementation = None

    if not request.node.get_closest_marker("django_db"):
        return
    if connection.needs_rollback:
        return

    request.getfixturevalue("db")
    try:
        reset()
    except NotImplementedError:
        pass

@pytest.fixture(autouse=True)
def ensure_global_pii_write_fence(request):
    """Keep the singleton global PII write-fence present for DB tests.

    The H4 migration seeds ``PiiGlobalWriteFence`` (pk=1), but a transactional
    test's flush truncates it, which would make later transactional mapped
    writes and fence tests fail closed on a spuriously missing global fence.
    Re-seed it (open) before each DB test to preserve the production invariant.
    """
    if not request.node.get_closest_marker("django_db"):
        return
    if connection.needs_rollback:
        return
    request.getfixturevalue("db")
    from apps.encryption.models import PiiGlobalWriteFence

    PiiGlobalWriteFence.objects.get_or_create(pk=1)


@pytest.fixture(autouse=True)
def evidence_objects_exist_by_default(monkeypatch):
    from apps.evidence import storage

    monkeypatch.setattr("apps.evidence.storage.object_exists", lambda key: True)

    def validate(object_key):
        if not storage.object_exists(object_key):
            raise storage.EvidenceObjectValidationError(
                "missing", "Evidence object was not found."
            )
        return storage.EvidenceValidationResult(size=123, content_type="image/jpeg")

    monkeypatch.setattr("apps.evidence.storage.validate_evidence_object", validate)

