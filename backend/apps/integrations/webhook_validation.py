"""Shared validation for chat webhook URLs (Slack + Slack-compatible Mattermost)."""
from urllib.parse import urlsplit

from rest_framework import serializers


def validate_webhook_url(value):
    """Blank clears; nonblank must be an absolute HTTPS URL with a hostname, no embedded
    credentials, and no fragment. Provider-agnostic (accepts self-hosted Mattermost hosts).
    Operates on plaintext, before the setter encrypts it."""
    raw = (value or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    if parts.scheme != "https" or not parts.hostname:
        raise serializers.ValidationError("Enter an absolute https:// webhook URL.")
    if parts.username or parts.password or "@" in parts.netloc:
        raise serializers.ValidationError("Webhook URL must not embed credentials.")
    if parts.fragment:
        raise serializers.ValidationError("Webhook URL must not contain a fragment.")
    return raw
