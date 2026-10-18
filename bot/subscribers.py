"""Telegram subscription commands: /start, /stop and the update offset."""

from __future__ import annotations

import logging
from typing import Callable, Iterable

from .store import Store

logger = logging.getLogger(__name__)

Notifier = Callable[[str, str], object]

START_COMMANDS = {"/start", "/subscribe"}
STOP_COMMANDS = {"/stop", "/unsubscribe"}

WELCOME = "Inscription enregistrée : tu recevras le meme du jour."
GOODBYE = "Désinscription effectuée. Envoie /start pour te réabonner."


def _command(message: dict) -> str:
    text = (message.get("text") or "").strip()
    if not text.startswith("/"):
        return ""
    return text.split()[0].split("@", 1)[0].lower()


def _chat_info(message: dict) -> tuple[str, str | None, str | None] | None:
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return None
    name = chat.get("title") or chat.get("first_name") or chat.get("username")
    return str(chat_id), chat.get("username"), name


def handle_updates(
    updates: Iterable[dict],
    store: Store,
    notifier: Notifier | None = None,
) -> tuple[int, int]:
    """Apply /start and /stop updates, then persist the next offset.

    Returns ``(added, removed)``.
    """
    added = 0
    removed = 0
    last_update_id: int | None = None

    for update in updates:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            last_update_id = (
                update_id if last_update_id is None else max(last_update_id, update_id)
            )

        message = update.get("message")
        if not isinstance(message, dict):
            continue
        command = _command(message)
        if command not in START_COMMANDS and command not in STOP_COMMANDS:
            continue
        info = _chat_info(message)
        if info is None:
            continue

        chat_id, username, name = info
        if command in START_COMMANDS:
            store.add_subscriber(chat_id, username=username, first_name=name)
            added += 1
            reply = WELCOME
            logger.info("Nouvel abonné : %s", chat_id)
        else:
            store.remove_subscriber(chat_id)
            removed += 1
            reply = GOODBYE
            logger.info("Désabonnement : %s", chat_id)

        if notifier is not None:
            try:
                notifier(chat_id, reply)
            except Exception as exc:  # a failed reply must not lose the update
                logger.warning("Réponse Telegram impossible (%s) : %s", chat_id, exc)

    if last_update_id is not None:
        store.set_offset(last_update_id + 1)
    return added, removed
