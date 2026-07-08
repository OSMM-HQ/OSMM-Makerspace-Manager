from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Max, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.integrations.email_templates_registry import STREAMS
from apps.integrations.models import EmailLog


EMAIL_STALLED_MINUTES = 15
WORKER_STALE_MINUTES = 10
WORKER_HEARTBEAT_CACHE_KEY = "integrations:celery_last_seen"


def record_worker_heartbeat():
    try:
        cache.set(WORKER_HEARTBEAT_CACHE_KEY, timezone.now().isoformat(), timeout=None)
    except Exception:
        return


def build_integration_health(makerspace):
    sections = {
        "email": _safe_section(lambda: _email_section(makerspace)),
        "deliveries_by_stream": _safe_section(lambda: _deliveries_by_stream_section(makerspace)),
        "smtp": _safe_section(lambda: _smtp_section(makerspace)),
        "telegram": _safe_section(lambda: _telegram_section(makerspace)),
        "worker": _safe_section(_worker_section),
    }
    # Keep the rollup deliberately simple: failed/stalled email, stale worker,
    # or any unknown subsection means a manager should inspect the integration.
    status = "ok"
    if any(_section_needs_attention(section) for section in sections.values()):
        status = "warn"
    if any(section.get("status") == "error" for section in sections.values()):
        status = "error"
    return {"status": status, **sections}


def _safe_section(builder):
    try:
        return builder()
    except Exception as exc:
        return {"status": "unknown", "detail": str(exc)[:200]}


def _email_section(makerspace):
    stalled_before = timezone.now() - timedelta(minutes=EMAIL_STALLED_MINUTES)
    counts = EmailLog.objects.filter(makerspace=makerspace).aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=EmailLog.Status.PENDING)),
        sent=Count("id", filter=Q(status=EmailLog.Status.SENT)),
        failed=Count("id", filter=Q(status=EmailLog.Status.FAILED)),
        stalled=Count(
            "id",
            filter=Q(status=EmailLog.Status.PENDING, created_at__lt=stalled_before),
        ),
    )
    last_failure = (
        EmailLog.objects.filter(makerspace=makerspace, status=EmailLog.Status.FAILED)
        .order_by("-created_at")
        .values("created_at", "subject", "error", "stream")
        .first()
    )
    if last_failure is not None:
        last_failure["error"] = (last_failure.get("error") or "")[:200]
    return {
        **counts,
        "last_failure": last_failure,
        "status": "warn" if counts["failed"] or counts["stalled"] else "ok",
    }


def _deliveries_by_stream_section(makerspace):
    latest_rows = (
        EmailLog.objects.filter(makerspace=makerspace, status=EmailLog.Status.SENT)
        .values("stream")
        .annotate(last_sent_at=Max("sent_at"))
    )
    latest_by_stream = {row["stream"]: row["last_sent_at"] for row in latest_rows}
    return {
        "status": "ok",
        **{stream: latest_by_stream.get(stream) for stream in sorted(STREAMS)},
    }


def _smtp_section(makerspace):
    return {"status": "ok", "configured": bool((makerspace.smtp_host or "").strip())}


def _telegram_section(makerspace):
    return {
        "status": "ok",
        "configured": bool((makerspace.telegram_bot_token or "").strip())
        and bool((makerspace.telegram_group_chat_id or "").strip()),
    }


def _worker_section():
    eager = bool(settings.CELERY_TASK_ALWAYS_EAGER)
    broker_configured = bool(settings.CELERY_BROKER_URL and not eager)
    last_seen = cache.get(WORKER_HEARTBEAT_CACHE_KEY)
    parsed_last_seen = _parse_cached_datetime(last_seen)
    stale = False
    if broker_configured:
        stale = parsed_last_seen is None or parsed_last_seen < (
            timezone.now() - timedelta(minutes=WORKER_STALE_MINUTES)
        )
    return {
        "status": "warn" if stale else "ok",
        "broker_configured": broker_configured,
        "eager": eager,
        "last_seen": last_seen,
        "stale": stale,
    }


def _parse_cached_datetime(value):
    if not value:
        return None
    if hasattr(value, "tzinfo"):
        parsed = value
    else:
        parsed = parse_datetime(str(value))
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone=timezone.utc)
    return parsed


def _section_needs_attention(section):
    if section.get("status") in {"warn", "unknown", "error"}:
        return True
    return bool(section.get("failed") or section.get("stalled") or section.get("stale"))