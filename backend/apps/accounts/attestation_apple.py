import hmac
from urllib.parse import urlsplit

import requests
from django.conf import settings

from apps.accounts.attestation import AttestationRejected, AttestationUnavailable


def verify_apple_attestation(challenge, raw_challenge, payload):
    return verify_with_provider(
        settings.DEVICE_APPLE_ATTESTATION_VERIFY_URL,
        settings.DEVICE_APPLE_ATTESTATION_VERIFY_TOKEN,
        challenge, raw_challenge, payload,
    )


def verify_with_provider(url, token, challenge, raw_challenge, payload):
    parsed_url = urlsplit(str(url or ''))
    if parsed_url.scheme != 'https' or not parsed_url.netloc or not token:
        raise AttestationUnavailable("Device attestation is unavailable.")
    try:
        response = requests.post(
            url,
            json={
                "challenge": raw_challenge, "platform": challenge.platform,
                "app_id": challenge.app_id,
                "signing_identity": challenge.signing_identity,
                "environment": challenge.environment, "attestation": payload,
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=settings.DEVICE_ATTESTATION_PROVIDER_TIMEOUT_SECONDS,
        )
        data = response.json() if response.status_code == 200 else {}
    except (requests.RequestException, ValueError) as exc:
        raise AttestationUnavailable("Device attestation is unavailable.") from exc
    expected = (
        challenge.platform,
        challenge.app_id,
        challenge.signing_identity,
        challenge.environment,
        raw_challenge,
    )
    actual = (
        data.get('platform'),
        data.get('app_id'),
        data.get('signing_identity'),
        data.get('environment'),
        data.get('challenge'),
    )
    claims_match = all(
        hmac.compare_digest(str(actual_value), str(expected_value))
        for actual_value, expected_value in zip(actual, expected)
    )
    if not data.get("verified") or not claims_match:
        raise AttestationRejected("Attestation was rejected.")
    return data.get("subject")
