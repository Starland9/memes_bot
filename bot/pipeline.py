"""Orchestration: news -> meme plan -> image -> Telegram."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Callable

import httpx

from .config import ConfigError, Settings
from .llm import DeepSeekClient, MemePlan
from .memegen import build_image_url, fetch_image
from .news import NewsItem, collect_news
from .safety import blocked_term
from .store import Store
from .subscribers import handle_updates
from .telegram import TelegramClient
from .templates import Template, fetch_templates, select_templates

logger = logging.getLogger(__name__)

NewsFetcher = Callable[[], list[NewsItem]]
TemplateFetcher = Callable[[], list[Template]]
Generator = Callable[[NewsItem, list[Template], tuple[str, ...]], MemePlan | None]
ImageFetcher = Callable[[str], bytes]
Publisher = Callable[[str, bytes, str], dict]
UpdateFetcher = Callable[[int | None], list[dict]]
Notifier = Callable[[str, str], object]


@dataclass(frozen=True)
class RunResult:
    status: str
    detail: str


def url_hash(url: str) -> str:
    return hashlib.sha256(url.split("?")[0].encode("utf-8")).hexdigest()[:32]


def _recipients(settings: Settings, store: Store) -> tuple[str, ...]:
    targets = list(store.subscribers())
    if settings.telegram_chat_id:
        targets.append(settings.telegram_chat_id)
    return tuple(dict.fromkeys(targets))


def _is_blocked(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        marker in text
        for marker in ("403", "blocked", "chat not found", "user is deactivated")
    )


def run_once(
    settings: Settings,
    *,
    store: Store | None = None,
    news_fetcher: NewsFetcher | None = None,
    template_fetcher: TemplateFetcher | None = None,
    generator: Generator | None = None,
    image_fetcher: ImageFetcher | None = None,
    publisher: Publisher | None = None,
    update_fetcher: UpdateFetcher | None = None,
    notifier: Notifier | None = None,
) -> RunResult:
    owns_store = store is None
    with httpx.Client(
        timeout=settings.request_timeout,
        headers={"User-Agent": "memegen-news-bot/0.1"},
    ) as client:
        store = store or Store(settings.data_dir / "bot.db")
        try:
            news_fetcher = news_fetcher or (lambda: collect_news(client, settings))
            template_fetcher = template_fetcher or (
                lambda: select_templates(fetch_templates(client, settings.memegen_base_url))
            )
            generator = generator or DeepSeekClient(
                client,
                settings.deepseek_api_key,
                settings.deepseek_base_url,
                settings.deepseek_model,
            ).generate
            image_fetcher = image_fetcher or (lambda url: fetch_image(client, url))

            recipients: tuple[str, ...] = ()
            if not settings.dry_run:
                telegram = TelegramClient(client, settings.telegram_bot_token)
                publisher = publisher or telegram.send_photo
                notifier = notifier or telegram.send_message
                fetcher: UpdateFetcher = update_fetcher or telegram.get_updates
                try:
                    added, removed = handle_updates(
                        fetcher(store.get_offset()), store, notifier
                    )
                    if added or removed:
                        logger.info(
                            "%d abonnement(s), %d désabonnement(s)", added, removed
                        )
                except Exception as exc:  # broadcast can proceed with known subscribers
                    logger.warning("Mise à jour des abonnés impossible : %s", exc)

                recipients = _recipients(settings, store)
                if not recipients:
                    return RunResult("nothing", "aucun abonné")

            items = news_fetcher()
            if not items:
                return RunResult("nothing", "aucune actualité fraîche")

            templates = template_fetcher()
            recent = store.recent_templates()

            for item in items:
                digest = url_hash(item.url)
                if store.is_seen(digest):
                    continue

                term = blocked_term(item.title)
                if term:
                    logger.info("Actualité ignorée (sujet sensible: %s) : %s", term, item.title)
                    store.record(
                        url_hash=digest,
                        url=item.url,
                        title=item.title,
                        source=item.source,
                        status="skipped_unsafe",
                        error=f"sujet sensible: {term}",
                    )
                    continue

                plan = generator(item, templates, recent)
                if plan is None:
                    logger.info("Le modèle a refusé de traiter : %s", item.title)
                    store.record(
                        url_hash=digest,
                        url=item.url,
                        title=item.title,
                        source=item.source,
                        status="skipped_model",
                        error="refus du modèle",
                    )
                    continue

                image_url = build_image_url(
                    settings.memegen_base_url, plan.template_id, plan.lines
                )
                logger.info("Meme %s : %s", plan.template_id, image_url)
                image = image_fetcher(image_url)

                if settings.dry_run:
                    out_dir = settings.data_dir / "out"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    path = out_dir / f"{digest}.png"
                    path.write_bytes(image)
                    store.record(
                        url_hash=digest,
                        url=item.url,
                        title=item.title,
                        source=item.source,
                        status="dry_run",
                        template_id=plan.template_id,
                        lines=plan.lines,
                        caption=plan.caption,
                    )
                    return RunResult("dry_run", f"{path} ({plan.template_id})")

                message_ids: list[str] = []
                for chat_id in recipients:
                    try:
                        message = publisher(chat_id, image, plan.caption)
                    except Exception as exc:
                        logger.warning("Envoi à %s impossible : %s", chat_id, exc)
                        if _is_blocked(exc):
                            store.remove_subscriber(chat_id)
                            logger.info("Abonné %s retiré (bot bloqué)", chat_id)
                        store.record_delivery(
                            url_hash=digest, chat_id=chat_id, error=str(exc)
                        )
                        continue

                    message_id = str(message.get("message_id", ""))
                    message_ids.append(message_id)
                    store.record_delivery(
                        url_hash=digest, chat_id=chat_id, message_id=message_id
                    )
                    logger.info("Publié pour %s (message %s)", chat_id, message_id)

                if not message_ids:
                    logger.error("Aucun envoi réussi pour : %s", item.title)
                    return RunResult("nothing", "aucun envoi réussi")

                store.record(
                    url_hash=digest,
                    url=item.url,
                    title=item.title,
                    source=item.source,
                    status="posted",
                    template_id=plan.template_id,
                    lines=plan.lines,
                    caption=plan.caption,
                    message_id=message_ids[0],
                )
                return RunResult(
                    "posted",
                    f"{len(message_ids)} destinataire(s) ({plan.template_id}) — {item.title}",
                )

            return RunResult("nothing", "toutes les actualités ont déjà été traitées")
        finally:
            if owns_store:
                store.close()


def poll_updates(
    settings: Settings,
    *,
    store: Store | None = None,
    update_fetcher: UpdateFetcher | None = None,
    notifier: Notifier | None = None,
) -> RunResult:
    """Process pending /start and /stop commands once."""
    if not settings.telegram_bot_token:
        raise ConfigError("TELEGRAM_BOT_TOKEN manquant pour relever les abonnés")

    owns_store = store is None
    with httpx.Client(
        timeout=settings.request_timeout,
        headers={"User-Agent": "memegen-news-bot/0.1"},
    ) as client:
        store = store or Store(settings.data_dir / "bot.db")
        try:
            telegram = TelegramClient(client, settings.telegram_bot_token)
            added, removed = handle_updates(
                (update_fetcher or telegram.get_updates)(store.get_offset()),
                store,
                notifier or telegram.send_message,
            )
            return RunResult(
                "updated", f"{added} abonnement(s), {removed} désabonnement(s)"
            )
        finally:
            if owns_store:
                store.close()
