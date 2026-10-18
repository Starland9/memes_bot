"""News collection from Google News (FR tech) and Hacker News."""

from __future__ import annotations

import html
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

from .config import Settings

logger = logging.getLogger(__name__)

GOOGLE_NEWS_FR_TECH = (
    "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY"
    "?hl=fr&gl=FR&ceid=FR:fr"
)
HN_TOP_STORIES = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    source: str
    published: datetime


def _parse_date(value: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_rss(xml_text: str, source: str) -> list[NewsItem]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("Flux RSS illisible (%s)", source)
        return []

    items: list[NewsItem] = []
    for node in root.iter("item"):
        title = html.unescape((node.findtext("title") or "").strip())
        link = (node.findtext("link") or "").strip()
        published = _parse_date(node.findtext("pubDate") or "")
        if title and link and published:
            items.append(NewsItem(title, link, source, published))
    return items


def fetch_google_news(client: httpx.Client, url: str = GOOGLE_NEWS_FR_TECH) -> list[NewsItem]:
    response = client.get(url, follow_redirects=True)
    response.raise_for_status()
    return parse_rss(response.text, "Google News FR")


def fetch_hackernews(
    client: httpx.Client,
    limit: int = 20,
    min_score: int = 100,
) -> list[NewsItem]:
    ids = client.get(HN_TOP_STORIES).json()[:limit]
    items: list[NewsItem] = []
    for story_id in ids:
        data = client.get(HN_ITEM.format(story_id)).json() or {}
        if data.get("type") != "story" or data.get("score", 0) < min_score:
            continue
        title = (data.get("title") or "").strip()
        if not title:
            continue
        url = data.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
        published = datetime.fromtimestamp(data.get("time", 0), tz=timezone.utc)
        items.append(NewsItem(title, url, "Hacker News", published))
    return items


def _normalize_url(url: str) -> str:
    return url.split("?")[0].rstrip("/")


def collect_news(client: httpx.Client, settings: Settings) -> list[NewsItem]:
    """Return fresh, de-duplicated news items, newest first."""
    sources = (
        ("google-news", lambda: fetch_google_news(client)),
        ("hacker-news", lambda: fetch_hackernews(client)),
    )

    raw: list[NewsItem] = []
    for name, fetcher in sources:
        try:
            raw.extend(fetcher())
        except Exception as exc:  # one broken source must not kill the run
            logger.warning("Source %s indisponible : %s", name, exc)

    if not raw:
        raise RuntimeError("aucune source d'actualité n'a répondu")

    now = datetime.now(timezone.utc)
    horizon = now - timedelta(hours=settings.max_age_hours)
    fresh = [
        item
        for item in raw
        if horizon <= item.published <= now + timedelta(hours=1)
    ]

    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[NewsItem] = []
    for item in sorted(fresh, key=lambda i: i.published, reverse=True):
        url_key = _normalize_url(item.url)
        title_key = item.title.casefold()
        if url_key in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        unique.append(item)

    logger.info(
        "%d actus récupérées, %d fraîches (< %sh), %d uniques",
        len(raw),
        len(fresh),
        settings.max_age_hours,
        len(unique),
    )
    return unique[: settings.max_news_items]
