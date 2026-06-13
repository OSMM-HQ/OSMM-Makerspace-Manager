import logging
import json
from urllib import request as urllib_request

from django.conf import settings

logger = logging.getLogger(__name__)


class TelegramDeliveryError(Exception):
    pass


def send_message(makerspace, text, reply_markup=None):
    token = (
        makerspace.get_telegram_bot_token()
        if hasattr(makerspace, "get_telegram_bot_token")
        else getattr(makerspace, "telegram_bot_token", "")
    ) or getattr(
        settings,
        "TELEGRAM_BOT_TOKEN",
        "",
    )
    chat_id = getattr(makerspace, "telegram_group_chat_id", "")
    if not token or not chat_id:
        logger.info(
            "Telegram delivery skipped.",
            extra={"makerspace_id": makerspace.pk, "configured": bool(token and chat_id)},
        )
        return False

    base_url = getattr(settings, "TELEGRAM_API_URL", "https://api.telegram.org").rstrip("/")
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        body = json.dumps(payload).encode()
        req = urllib_request.Request(
            f"{base_url}/bot{token}/sendMessage",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=5) as response:
            if response.status >= 400:
                raise TelegramDeliveryError("Telegram delivery failed.")
    except Exception as exc:
        logger.warning(
            "Telegram delivery failed.",
            extra={"makerspace_id": makerspace.pk},
            exc_info=exc,
        )
        raise TelegramDeliveryError("Telegram delivery failed.") from exc
    return True
