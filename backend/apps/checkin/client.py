import logging
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)


class CheckinUnavailable(Exception):
    pass


class CheckinDenied(Exception):
    pass


@dataclass(frozen=True)
class CheckinResult:
    username: str
    external_id: str


def verify(makerspace, identifier) -> CheckinResult:
    mode = (getattr(settings, "CHECKIN_MODE", "stub") or "stub").lower()
    slug = getattr(makerspace, "slug", "")

    if mode == "stub":
        return _verify_stub(identifier)
    if mode == "http":
        return _verify_http(makerspace, identifier)

    logger.warning("Unknown check-in mode.", extra={"mode": mode, "makerspace": slug})
    raise CheckinUnavailable("Check-in service is not configured.")


def _verify_stub(identifier) -> CheckinResult:
    normalized = str(identifier or "").strip()
    if not normalized:
        raise CheckinDenied("Identifier is required.")
    return CheckinResult(username=normalized, external_id=normalized)


def _verify_http(makerspace, identifier) -> CheckinResult:
    import requests

    mode = "http"
    slug = getattr(makerspace, "slug", "")
    url = getattr(settings, "CHECKIN_API_URL", "")
    api_key = getattr(settings, "CHECKIN_API_KEY", "")
    timeout = getattr(settings, "CHECKIN_TIMEOUT", 5.0)
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    try:
        response = requests.post(
            url,
            json={"identifier": identifier, "makerspace": slug},
            headers=headers,
            timeout=timeout,
        )
    except (requests.ConnectionError, requests.Timeout) as exc:
        logger.warning(
            "Check-in service unreachable.",
            extra={"mode": mode, "makerspace": slug, "error_class": type(exc).__name__},
        )
        raise CheckinUnavailable("Check-in service is unavailable.") from exc
    except requests.RequestException as exc:
        logger.warning(
            "Check-in request failed.",
            extra={"mode": mode, "makerspace": slug, "error_class": type(exc).__name__},
        )
        raise CheckinUnavailable("Check-in service is unavailable.") from exc

    # 404 == "service healthy, identifier not checked in" -> deny (403).
    # 401/403 are intentionally NOT treated as denial: they are ambiguous (our client's
    # credentials rejected vs. the identifier rejected). We cannot distinguish them
    # generically, so we fail closed to 503 below. The exact denial shape of the real
    # check-in API is an open question (PRD §18) and will be pinned when http mode is wired.
    if response.status_code == 404:
        logger.warning(
            "Check-in identifier denied.",
            extra={"mode": mode, "makerspace": slug, "status_code": response.status_code},
        )
        raise CheckinDenied("Identifier is not checked in.")

    # Fail-closed BEFORE parsing any denial body: every non-2xx status other than the
    # explicit 404 above (401/403/5xx/...) is ambiguous, so it maps to 503 and never to a
    # denial. Denial signals are only honored on a 404 or a successful (2xx) response body.
    if not response.ok:
        logger.warning(
            "Check-in service returned an unsuccessful status.",
            extra={"mode": mode, "makerspace": slug, "status_code": response.status_code},
        )
        raise CheckinUnavailable("Check-in service is unavailable.")

    data = _response_json(response, mode, slug)

    if _is_denied_response(data):
        logger.warning(
            "Check-in identifier denied.",
            extra={"mode": mode, "makerspace": slug, "status_code": response.status_code},
        )
        raise CheckinDenied("Identifier is not checked in.")

    username = data.get("username")
    if not isinstance(username, str) or not username.strip():
        logger.warning(
            "Check-in service returned a malformed response.",
            extra={"mode": mode, "makerspace": slug, "status_code": response.status_code},
        )
        raise CheckinUnavailable("Check-in service returned an invalid response.")

    external_id = data.get("external_id") or identifier
    return CheckinResult(username=username.strip(), external_id=str(external_id))


def _response_json(response, mode, slug):
    try:
        data = response.json()
    except ValueError as exc:
        logger.warning(
            "Check-in service returned non-JSON response.",
            extra={"mode": mode, "makerspace": slug, "status_code": response.status_code, "error_class": type(exc).__name__},
        )
        raise CheckinUnavailable("Check-in service returned an invalid response.") from exc

    if not isinstance(data, dict):
        logger.warning(
            "Check-in service returned non-object JSON.",
            extra={"mode": mode, "makerspace": slug, "status_code": response.status_code},
        )
        raise CheckinUnavailable("Check-in service returned an invalid response.")
    return data


def _is_denied_response(data):
    if data.get("verified") is False:
        return True

    code = str(data.get("code") or data.get("error") or "").lower()
    return code in {"denied", "invalid", "not_checked_in", "not_checked-in"}
