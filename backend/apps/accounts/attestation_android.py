from django.conf import settings

from apps.accounts.attestation_apple import verify_with_provider


def verify_android_attestation(challenge, raw_challenge, payload):
    return verify_with_provider(
        settings.DEVICE_ANDROID_ATTESTATION_VERIFY_URL,
        settings.DEVICE_ANDROID_ATTESTATION_VERIFY_TOKEN,
        challenge, raw_challenge, payload,
    )
