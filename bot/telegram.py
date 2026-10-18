"""Publish memes and handle subscriptions through the Telegram Bot API."""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)


class TelegramError(RuntimeError):
    """Telegram rejected the request."""


class TelegramClient:
    def __init__(self, client: httpx.Client, token: str) -> None:
        self._client = client
        self._token = token

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self._token}/{method}"

    def _result(self, response: httpx.Response) -> dict:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.is_success and payload.get("ok"):
            return payload["result"]
        description = payload.get("description") or response.text[:200]
        raise TelegramError(f"HTTP {response.status_code} : {description}")

    def send_photo(self, chat_id: str, image: bytes, caption: str) -> dict:
        for attempt in range(2):
            response = self._client.post(
                self._url("sendPhoto"),
                data={"chat_id": chat_id, "caption": caption},
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

    def send_message(self, chat_id: str, text: str) -> dict:
        response = self._client.post(
            self._url("sendMessage"),
            data={"chat_id": chat_id, "text": text},
        )
        return self._result(response)

    def get_updates(self, offset: int | None = None, timeout: int = 0) -> list[dict]:
        params: dict[str, int] = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        response = self._client.get(self._url("getUpdates"), params=params)
        return list(self._result(response) or [])
