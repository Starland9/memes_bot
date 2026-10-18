"""Publish memes to a Telegram chat or channel."""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)


class TelegramError(RuntimeError):
    """Telegram rejected the request."""


class TelegramClient:
    def __init__(self, client: httpx.Client, token: str, chat_id: str) -> None:
        self._client = client
        self._token = token
        self._chat_id = chat_id

    def send_photo(self, image: bytes, caption: str) -> dict:
        url = f"https://api.telegram.org/bot{self._token}/sendPhoto"
        for attempt in range(2):
            response = self._client.post(
                url,
                data={"chat_id": self._chat_id, "caption": caption},
                files={"photo": ("meme.png", image, "image/png")},
            )
            try:
                payload = response.json()
            except ValueError:
                payload = {}

            if response.is_success and payload.get("ok"):
                return payload["result"]

            if response.status_code == 429 and attempt == 0:
                retry_after = int(payload.get("parameters", {}).get("retry_after", 3))
                delay = min(max(retry_after, 1), 60)
                logger.warning("Limite Telegram atteinte, nouvelle tentative dans %ss", delay)
                time.sleep(delay)
                continue

            description = payload.get("description") or response.text[:200]
            raise TelegramError(f"HTTP {response.status_code} : {description}")

        raise TelegramError("échec de l'envoi après nouvelle tentative")
