"""P3 — proxy-aware throttle client-IP resolution (NUM_PROXIES).

DRF's throttle identity comes from BaseThrottle.get_ident(). Without NUM_PROXIES it
falls back to REMOTE_ADDR (or the raw X-Forwarded-For string). Setting NUM_PROXIES to
the trusted proxy count makes it key on the real client IP — the Nth-from-last XFF
entry — so a CDN/reverse proxy deployment throttles per real client, not per proxy IP.
"""
from rest_framework.settings import api_settings
from rest_framework.test import APIRequestFactory
from rest_framework.throttling import BaseThrottle


def _ident(**meta):
    request = APIRequestFactory().get("/", **meta)
    # BaseThrottle.get_ident reads request.META and api_settings.NUM_PROXIES. (Use the
    # base class, not SimpleRateThrottle, which requires a configured scope at init.)
    return BaseThrottle().get_ident(request)


def test_default_unset_uses_remote_addr_or_raw_xff(settings):
    # Default (no NUM_PROXIES) is DRF's legacy behavior: with no XFF, REMOTE_ADDR wins.
    assert api_settings.NUM_PROXIES is None
    assert _ident(REMOTE_ADDR="10.0.0.9") == "10.0.0.9"


def test_num_proxies_one_takes_real_client_from_xff(settings):
    # One trusted proxy: DRF counts from the right, so the real client is the LAST XFF
    # entry (the one our proxy appended). A client-spoofed prefix ("1.2.3.4") is ignored,
    # and the proxy's own REMOTE_ADDR ("172.16.0.1") is not used as the throttle key.
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 1}
    api_settings.reload()
    try:
        ident = _ident(
            HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.7",
            REMOTE_ADDR="172.16.0.1",
        )
        assert ident == "203.0.113.7"
    finally:
        api_settings.reload()


def test_num_proxies_zero_ignores_xff(settings):
    # Zero trusted proxies: XFF is untrusted, REMOTE_ADDR wins even when XFF is spoofed.
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 0}
    api_settings.reload()
    try:
        ident = _ident(
            HTTP_X_FORWARDED_FOR="1.2.3.4",
            REMOTE_ADDR="172.16.0.1",
        )
        assert ident == "172.16.0.1"
    finally:
        api_settings.reload()
