"""Publish memes to a WhatsApp status or channel through an OpenWA gateway."""

from __future__ import annotations

import base64
import re
from typing import Any
from urllib.parse import quote

import httpx

MAX_CAPTION_LENGTH = 1024
MAX_TEXT_LENGTH = 4096
MAX_CONTACTS = 100_000
CONTACTS_PAGE_SIZE = 1000
CHANNEL_LINK_RE = re.compile(r"whatsapp\.com/channel/([A-Za-z0-9_-]+)")
CHANNEL_INVITE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def parse_channel_invite(value: str) -> str:
    """Extract the invite code from a WhatsApp channel share link."""
    text = value.strip()
    match = CHANNEL_LINK_RE.search(text)
    code = match.group(1) if match else text
    if not CHANNEL_INVITE_RE.fullmatch(code):
        raise ValueError(f"lien de chaîne invalide : {value}")
    return code


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

    def subscribe_channel(self, invite_code: str) -> dict:
        """Resolve an invite code and return the channel, which carries its `@newsletter` id.

        OpenWA implements this as a metadata lookup followed by a follow, so the session
        ends up subscribed to the channel. It is the only route that resolves an invite.
        """
        response = self._client.post(
            self._session_url("channels/subscribe"),
            json={"inviteCode": invite_code},
            headers={"X-API-Key": self._api_key},
        )
        body = self._decode(response)
        return body if isinstance(body, dict) else {}

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

    def send_text_message(self, chat_id: str, text: str) -> dict:
        """Post a text message to a chat, a group or a channel.

        Works on channels where media does not: Baileys still uploads newsletter media
        through the regular media endpoints, so WhatsApp drops the image (ack error 479).
        """
        response = self._client.post(
            self._session_url("messages/send-text"),
            json={"chatId": chat_id, "text": text[:MAX_TEXT_LENGTH]},
            headers={"X-API-Key": self._api_key},
        )
        body = self._decode(response)
        return body if isinstance(body, dict) else {}

    def send_image_message(self, chat_id: str, image: bytes, caption: str) -> dict:
        """Post an image to a chat, a group or a channel (`<id>@newsletter`)."""
        payload: dict[str, object] = {
            "chatId": chat_id,
            "base64": base64.b64encode(image).decode("ascii"),
            "mimetype": "image/png",
        }
        if caption:
            payload["caption"] = caption[:MAX_CAPTION_LENGTH]

        response = self._client.post(
            self._session_url("messages/send-image"),
            json=payload,
            headers={"X-API-Key": self._api_key},
        )
        body = self._decode(response)
        return body if isinstance(body, dict) else {}
