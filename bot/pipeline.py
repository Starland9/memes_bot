"""Orchestration: news -> meme plan -> image -> Telegram + WhatsApp status."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import httpx

from .config import ConfigError, Settings
from .llm import DeepSeekClient, MemePlan
from .memegen import build_image_url, fetch_image
from .news import NewsItem, collect_news
from .openwa import OpenWAClient
from .safety import blocked_term
from .store import Store
from .subscribers import handle_updates
from .telegram import TelegramClient
from .templates import Template, fetch_templates, select_templates

logger = logging.getLogger(__name__)

STATUS_TARGET = "whatsapp-status"
MAX_STATUS_RECIPIENTS = 256

NewsFetcher = Callable[[], list[NewsItem]]
TemplateFetcher = Callable[[], list[Template]]
Generator = Callable[[NewsItem, list[Template], tuple[str, ...]], MemePlan | None]
ImageFetcher = Callable[[str], bytes]
Publisher = Callable[[str, bytes, str], dict]
StatusPublisher = Callable[[bytes, str], dict]
UpdateFetcher = Callable[[int | None], list[dict]]
Notifier = Callable[[str, str], object]
ContactFetcher = Callable[[], list[dict]]


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


def _status_recipients(settings: Settings, store: Store) -> tuple[str, ...]:
    targets = list(settings.openwa_status_recipients)
    if settings.openwa_status_use_contacts:
        since = None
        if settings.openwa_status_chat_days > 0:
            since = int(
                datetime.now(timezone.utc).timestamp()
                - settings.openwa_status_chat_days * 86400
            )
        stored = store.whatsapp_contacts(
            limit=MAX_STATUS_RECIPIENTS,
            chatted_only=settings.openwa_status_chatted_only,
            since=since,
        )
        if not stored:
            if settings.openwa_status_chatted_only or settings.openwa_status_chat_days > 0:
                logger.warning(
                    "Aucun contact WhatsApp ne correspond au filtre de discussions : "
                    "relance `python -m bot --sync-contacts`"
                )
            else:
                logger.warning(
                    "Aucun contact WhatsApp en cache : lance `python -m bot --sync-contacts`"
                )
        targets.extend(stored)
    return tuple(dict.fromkeys(targets))[:MAX_STATUS_RECIPIENTS]


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
    status_publisher: StatusPublisher | None = None,
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
            status_sender = status_publisher
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
                if status_sender is None and settings.openwa_configured:
                    status_sender = OpenWAClient(
                        client,
                        settings.openwa_base_url,
                        settings.openwa_api_key,
                        settings.openwa_session_id,
                        _status_recipients(settings, store),
                    ).send_image_status
                if not recipients and status_sender is None:
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

                status_posted = False
                if status_sender is not None:
                    try:
                        status = status_sender(image, plan.caption)
                    except Exception as exc:
                        logger.warning("Publication du statut WhatsApp impossible : %s", exc)
                        store.record_delivery(
                            url_hash=digest, chat_id=STATUS_TARGET, error=str(exc)
                        )
                    else:
                        status_id = str(status.get("id", ""))
                        status_posted = True
                        store.record_delivery(
                            url_hash=digest,
                            chat_id=STATUS_TARGET,
                            message_id=status_id,
                        )
                        logger.info("Publié en statut WhatsApp (id %s)", status_id or "absent")

                if not message_ids and not status_posted:
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
                    message_id=message_ids[0] if message_ids else None,
                )
                targets: list[str] = []
                if message_ids:
                    targets.append(f"{len(message_ids)} destinataire(s)")
                if status_posted:
                    targets.append("statut WhatsApp")
                return RunResult(
                    "posted",
                    f"{' + '.join(targets)} ({plan.template_id}) — {item.title}",
                )

            return RunResult("nothing", "toutes les actualités ont déjà été traitées")
        finally:
            if owns_store:
                store.close()


def sync_contacts(
    settings: Settings,
    *,
    store: Store | None = None,
    contact_fetcher: ContactFetcher | None = None,
    chat_fetcher: ContactFetcher | None = None,
) -> RunResult:
    """Cache the OpenWA address book (and chats) for WhatsApp status recipients."""
    if not settings.openwa_configured:
        raise ConfigError(
            "Configuration OpenWA requise pour synchroniser les contacts"
        )

    wants_chats = (
        settings.openwa_status_chatted_only or settings.openwa_status_chat_days > 0
    )

    owns_store = store is None
    with httpx.Client(
        timeout=settings.request_timeout,
        headers={"User-Agent": "memegen-news-bot/0.1"},
    ) as client:
        store = store or Store(settings.data_dir / "bot.db")
        try:
            openwa = OpenWAClient(
                client,
                settings.openwa_base_url,
                settings.openwa_api_key,
                settings.openwa_session_id,
            )
            contacts = (contact_fetcher or openwa.list_contacts)()
            chats: list[dict] = []
            if wants_chats:
                try:
                    chats = (chat_fetcher or openwa.list_chats)()
                except Exception as exc:  # the address book alone still refreshes the cache
                    logger.warning(
                        "Liste des discussions indisponible, filtre ignoré : %s", exc
                    )

            count = store.replace_whatsapp_contacts(contacts, chats)
            since = None
            if settings.openwa_status_chat_days > 0:
                since = int(
                    datetime.now(timezone.utc).timestamp()
                    - settings.openwa_status_chat_days * 86400
                )
            usable = store.whatsapp_contacts(
                limit=MAX_STATUS_RECIPIENTS,
                chatted_only=settings.openwa_status_chatted_only,
                since=since,
            )
            return RunResult(
                "synced",
                f"{count} contact(s) WhatsApp, "
                f"{len(usable)} destinataire(s) de statut",
            )
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
