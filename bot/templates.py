"""Meme templates exposed by the memegen API."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

# Templates whose visual structure is easy to map to a short joke.
# All of them are validated against the API at runtime: unknown IDs are dropped.
CURATED_TEMPLATE_IDS: tuple[str, ...] = (
    "drake",
    "fry",
    "both",
    "db",
    "gru",
    "panik-kalm-panik",
    "ds",
    "doge",
    "buzz",
    "oprah",
    "success",
    "interesting",
    "iw",
    "blb",
    "sadfrog",
    "fine",
    "money",
    "mb",
    "bad",
    "yuno",
    "aag",
    "badchoice",
    "biw",
    "facepalm",
    "fwp",
    "grumpycat",
    "leo",
    "mordor",
    "stonks",
    "toohigh",
    "whatyear",
    "astronaut",
    "gb",
    "handshake",
    "morpheus",
    "philosoraptor",
    "harold",
    "keanu",
    "vince",
    "cheems",
    "disastergirl",
    "dodgson",
    "midwit",
    "spiderman",
    "patrick",
    "pooh",
    "yodawg",
    "snek",
    "rollsafe",
    "nice",
    "kermit",
    "wonka",
    "spongebob",
    "cmm",
    "dg",
)


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    lines: int


def fetch_templates(client: httpx.Client, base_url: str) -> dict[str, Template]:
    response = client.get(f"{base_url}/templates/")
    response.raise_for_status()
    templates: dict[str, Template] = {}
    for entry in response.json():
        template_id = entry.get("id")
        lines = entry.get("lines")
        if not template_id or not isinstance(lines, int):
            continue
        templates[template_id] = Template(
            id=template_id,
            name=entry.get("name") or template_id,
            lines=lines,
        )
    return templates


def select_templates(available: dict[str, Template]) -> list[Template]:
    selected = [available[tid] for tid in CURATED_TEMPLATE_IDS if tid in available]
    missing = [tid for tid in CURATED_TEMPLATE_IDS if tid not in available]
    if missing:
        logger.info("Templates absents de l'API : %s", ", ".join(missing))
    if not selected:
        raise RuntimeError("aucun template exploitable dans l'API memegen")
    return selected
