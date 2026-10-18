"""Publish memes to a WhatsApp status through an OpenWA gateway."""

from __future__ import annotations

import base64
from urllib.parse import quote

import httpx

MAX_CAPTION_LENGTH = 1024


class OpenWAError(RuntimeError):
    """OpenWA rejected the status post."""


class OpenWAClient:
    def __init__(
        self,
        client: httpx.Client,
        base_url: str,
        api_key: str,
        session_id: str,
        recipients: tuple[str, ...] = (),
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._session_id = session_id
        self._recipients = recipients

    def _url(self) -> str:
        session = quote(self._session_id, safe="")
        return f"{self._base_url}/api/sessions/{session}/status/send-image"

    def send_image_status(self, image: bytes, caption: str) -> dict:
        payload: dict[str, object] = {
            "image": {
                "base64": base64.b64encode(image).decode("ascii"),
                "mimetype": "image/png",
            }
        }
        if caption:
            payload["caption"] = caption[:MAX_CAPTION_LENGTH]
        if self._recipients:
            payload["recipients"] = list(self._recipients)

        response = self._client.post(
            self._url(),
            json=payload,
            headers={"X-API-Key": self._api_key},
        )
        try:
            body = response.json()
        except ValueError:
            body = {}

        if response.is_success:
            return body if isinstance(body, dict) else {}

        message = response.text[:200]
        if isinstance(body, dict):
            message = body.get("message") or body.get("error") or message
        raise OpenWAError(f"HTTP {response.status_code} : {message}")
