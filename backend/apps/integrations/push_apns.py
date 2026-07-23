import time

import httpx
import jwt

from apps.integrations.push_fcm import PushProviderError


def send_apns(settings_row, token, environment, title, body, data):
    try:
        private_key = settings_row.get_apns_private_key()
        if not private_key or not settings_row.apns_team_id or not settings_row.apns_key_id or not settings_row.apns_topic:
            raise ValueError
        authorization = jwt.encode(
            {"iss": settings_row.apns_team_id, "iat": int(time.time())},
            private_key, algorithm="ES256", headers={"kid": settings_row.apns_key_id},
        )
    except (ValueError, TypeError) as exc:
        raise PushProviderError("APNs configuration is unavailable.") from exc
    host = "api.sandbox.push.apple.com" if environment == "development" else "api.push.apple.com"
    try:
        with httpx.Client(http2=True, timeout=10) as client:
            response = client.post(
                f"https://{host}/3/device/{token}",
                headers={
                    "authorization": f"bearer {authorization}",
                    "apns-topic": settings_row.apns_topic,
                    "apns-push-type": "alert",
                },
                json={"aps": {"alert": {"title": title, "body": body}}, "data": data},
            )
    except httpx.HTTPError as exc:
        raise PushProviderError("APNs request failed.") from exc
    if response.status_code == 200:
        return
    try:
        reason = response.json().get("reason", "")
    except ValueError:
        reason = ""
    raise PushProviderError(
        "APNs delivery failed.", invalid_token=reason in {"BadDeviceToken", "Unregistered"}
    )
