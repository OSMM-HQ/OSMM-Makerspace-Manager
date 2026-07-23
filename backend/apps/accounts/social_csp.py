from django.core.cache import cache


SOCIAL_CSP_CACHE_KEY = "platform-social-csp-origins"


def clear_social_csp_cache():
    cache.delete(SOCIAL_CSP_CACHE_KEY)


def social_csp_origins():
    cached = cache.get(SOCIAL_CSP_CACHE_KEY)
    if cached is not None:
        return cached
    from apps.accounts.models_social import PlatformSocialAuthSettings

    row = PlatformSocialAuthSettings.objects.filter(pk=1).first()
    origins = {}
    if row and row.google_web_client_id:
        origins["google"] = (
            "https://accounts.google.com",
            "https://oauth2.googleapis.com",
        )
    if row and row.apple_service_id:
        origins["apple"] = (
            "https://appleid.cdn-apple.com",
            "https://appleid.apple.com",
        )
    cache.set(SOCIAL_CSP_CACHE_KEY, origins, 60)
    return origins


class SocialCspMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        header = response.get("Content-Security-Policy")
        if not header or not response.get("Content-Type", "").startswith("text/html"):
            return response
        origins = social_csp_origins()
        if not origins:
            return response
        directives = _parse(header)
        if "google" in origins:
            _append(directives, "script-src", origins["google"][0])
            _append(directives, "frame-src", origins["google"][0])
            _append(directives, "connect-src", *origins["google"])
        if "apple" in origins:
            _append(directives, "script-src", origins["apple"][0])
            _append(directives, "frame-src", origins["apple"][1])
            _append(directives, "connect-src", origins["apple"][1])
        response["Content-Security-Policy"] = "; ".join(
            f"{name} {' '.join(values)}" for name, values in directives.items()
        )
        return response


def _parse(header):
    result = {}
    for part in header.split(";"):
        pieces = part.strip().split()
        if pieces:
            result[pieces[0]] = pieces[1:]
    return result


def _append(directives, name, *values):
    current = directives.setdefault(name, ["'self'"])
    for value in values:
        if value not in current:
            current.append(value)
