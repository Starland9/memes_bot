"""Publish memes to a WhatsApp status through an OpenWA gateway."""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import quote

import httpx

MAX_CAPTION_LENGTH = 1024
MAX_CONTACTS = 100_000
CONTACTS_PAGE_SIZE = 1000


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

    def _session_url(self, suffix: str) -> str:
        session = quote(self._session_id, safe="")
        return f"{self._base_url}/api/sessions/{session}/{suffix}"

    def _decode(self, response: httpx.Response) -> Any:
        try:
            body = response.json()
        except ValueError:
            body = None

        if response.is_success:
            return body

        message = response.text[:200]
        if isinstance(body, dict):
            message = body.get("message") or body.get("error") or message
        raise OpenWAError(f"HTTP {response.status_code} : {message}")

    def _list_paged(
        self, suffix: str, page_size: int, label: str
    ) -> list[dict]:
        """Fetch a paged OpenWA collection until the last short window."""
        items: list[dict] = []
        seen: set[str] = set()
        offset = 0
        while offset < MAX_CONTACTS:
            response = self._client.get(
                self._session_url(suffix),
                params={"limit": page_size, "offset": offset},
                headers={"X-API-Key": self._api_key},
            )
            body = self._decode(response)
            if not isinstance(body, list):
                raise OpenWAError(f"réponse inattendue de la liste {label}")

            added = 0
            for item in body:
                if not isinstance(item, dict):
                    continue
                item_id = item.get("id")
                if isinstance(item_id, str) and item_id:
                    if item_id in seen:
                        continue
                    seen.add(item_id)
                items.append(item)
                added += 1

            if len(body) < page_size or added == 0:
                break
            offset += len(body)
        return items

    def list_contacts(self, page_size: int = CONTACTS_PAGE_SIZE) -> list[dict]:
        """Fetch every contact of the session, paging through the gateway."""
        return self._list_paged("contacts", page_size, "des contacts")

    def list_chats(self, page_size: int = CONTACTS_PAGE_SIZE) -> list[dict]:
        """Fetch every active chat, most recent first (OpenWA's own ordering)."""
        return self._list_paged("chats", page_size, "des discussions")

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
            self._session_url("status/send-image"),
            json=payload,
            headers={"X-API-Key": self._api_key},
        )
        body = self._decode(response)
        return body if isinstance(body, dict) else {}
