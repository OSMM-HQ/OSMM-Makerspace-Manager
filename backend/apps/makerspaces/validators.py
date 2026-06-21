from urllib.parse import urlsplit

from django.core.exceptions import ValidationError


GOOGLE_MAPS_HOSTS = {
    "google.com",
    "www.google.com",
    "maps.google.com",
    "maps.app.goo.gl",
    "goo.gl",
    "g.co",
}
GOOGLE_MAPS_ERROR = "Enter a valid Google Maps link."


def validate_google_maps_url(value):
    if not (value or "").strip():
        return

    parsed = urlsplit(value)
    host = parsed.hostname
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or host not in GOOGLE_MAPS_HOSTS
    ):
        raise ValidationError(GOOGLE_MAPS_ERROR)

    path = parsed.path or ""
    if host in {"google.com", "www.google.com"} and not path.startswith("/maps"):
        raise ValidationError(GOOGLE_MAPS_ERROR)
    if host == "goo.gl" and not path.startswith("/maps"):
        raise ValidationError(GOOGLE_MAPS_ERROR)
    if host == "g.co" and not path.startswith("/kgs"):
        raise ValidationError(GOOGLE_MAPS_ERROR)
