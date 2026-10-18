"""Build and download memes through the memegen HTTP API."""

from __future__ import annotations

from urllib.parse import quote

import httpx

MAX_IMAGE_BYTES = 5 * 1024 * 1024


def build_image_url(
    base_url: str,
    template_id: str,
    lines: tuple[str, ...] | list[str],
    extension: str = "png",
) -> str:
    """Encode lines the way memegen expects (underscores for spaces, percent-encoding)."""
    encoded_lines = "/".join(
        quote(line.strip().replace(" ", "_"), safe="") for line in lines
    )
    return (
        f"{base_url.rstrip('/')}/images/{quote(template_id, safe='')}"
        f"/{encoded_lines}.{extension}"
    )


def fetch_image(client: httpx.Client, url: str) -> bytes:
    response = client.get(url, follow_redirects=True)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("image/"):
        raise RuntimeError(f"réponse inattendue de memegen ({content_type or 'sans type'})")
    data = response.content
    if len(data) > MAX_IMAGE_BYTES:
        raise RuntimeError(f"image trop lourde pour Telegram : {len(data)} octets")
    return data
