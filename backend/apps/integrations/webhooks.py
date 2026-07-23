import json
import logging
from urllib import request as urllib_request

logger = logging.getLogger(__name__)


class WebhookDeliveryError(Exception):
    pass


def send_webhook(makerspace, *, channel: str, text: str) -> bool:
    if channel not in {"slack", "mattermost"}:
        raise ValueError(f"Unsupported webhook channel: {channel}")

    if channel == "slack":
        url = makerspace.get_slack_webhook_url()
    else:
        url = makerspace.get_mattermost_webhook_url()
    if not url:
        return False

    try:
        req = urllib_request.Request(
            url,
            data=json.dumps({"text": text}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=5) as response:
            if response.status >= 400:
                raise WebhookDeliveryError("Webhook delivery failed.")
        return True
    except Exception as exc:
        logger.warning(
            "Webhook delivery failed.",
            extra={"makerspace_id": makerspace.pk, "channel": channel},
        )
        raise WebhookDeliveryError("Webhook delivery failed.") from exc
