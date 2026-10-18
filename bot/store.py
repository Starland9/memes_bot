"""SQLite state: posts, subscribers, deliveries and the Telegram offset."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path

CONTACT_ID_RE = re.compile(r"^\d+@(c\.us|lid)$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    url_hash    TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    title       TEXT NOT NULL,
    source      TEXT,
    template_id TEXT,
    lines       TEXT,
    caption     TEXT,
    message_id  TEXT,
    status      TEXT NOT NULL,
    error       TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subscribers (
    chat_id       TEXT PRIMARY KEY,
    username      TEXT,
    first_name     TEXT,
    subscribed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deliveries (
    url_hash   TEXT NOT NULL,
    chat_id    TEXT NOT NULL,
    message_id TEXT,
    error      TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (url_hash, chat_id)
);

CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS whatsapp_contacts (
    contact_id    TEXT PRIMARY KEY,
    number        TEXT,
    name          TEXT,
    push_name     TEXT,
    is_my_contact INTEGER NOT NULL DEFAULT 0,
    is_blocked    INTEGER NOT NULL DEFAULT 0,
    synced_at     TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class Store:
    def __init__(self, path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeError(
                f"DATA_DIR non inscriptible : {path.parent} ({exc})"
            ) from exc
        self._conn = sqlite3.connect(path)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def is_seen(self, url_hash: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM posts WHERE url_hash = ?", (url_hash,)
        ).fetchone()
        return row is not None

    def record(
        self,
        *,
        url_hash: str,
        url: str,
        title: str,
        source: str,
        status: str,
        template_id: str | None = None,
        lines: tuple[str, ...] = (),
        caption: str | None = None,
        message_id: str | None = None,
        error: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO posts
                (url_hash, url, title, source, template_id, lines, caption,
                 message_id, status, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                url_hash,
                url,
                title,
                source,
                template_id,
                json.dumps(list(lines), ensure_ascii=False),
                caption,
                message_id,
                status,
                error,
                _now(),
            ),
        )
        self._conn.commit()

    def recent_templates(self, limit: int = 10) -> tuple[str, ...]:
        rows = self._conn.execute(
            """
            SELECT template_id FROM posts
            WHERE template_id IS NOT NULL
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return tuple(row[0] for row in rows)

    def add_subscriber(
        self,
        chat_id: str,
        username: str | None = None,
        first_name: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO subscribers (chat_id, username, first_name, subscribed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
            """,
            (chat_id, username, first_name, _now()),
        )
        self._conn.commit()

    def remove_subscriber(self, chat_id: str) -> None:
        self._conn.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
        self._conn.commit()

    def subscribers(self) -> tuple[str, ...]:
        rows = self._conn.execute(
            "SELECT chat_id FROM subscribers ORDER BY subscribed_at"
        ).fetchall()
        return tuple(row[0] for row in rows)

    def replace_whatsapp_contacts(
        self, contacts: Iterable[Mapping[str, object]]
    ) -> int:
        """Replace the cached OpenWA address book with a fresh snapshot."""
        rows: dict[str, tuple] = {}
        synced_at = _now()
        for contact in contacts:
            contact_id = str(contact.get("id") or "").strip()
            if not CONTACT_ID_RE.fullmatch(contact_id):
                continue
            rows[contact_id] = (
                contact_id,
                _optional_text(contact.get("number")),
                _optional_text(contact.get("name")),
                _optional_text(contact.get("pushName")),
                1 if contact.get("isMyContact") else 0,
                1 if contact.get("isBlocked") else 0,
                synced_at,
            )

        with self._conn:
            self._conn.execute("DELETE FROM whatsapp_contacts")
            self._conn.executemany(
                """
                INSERT INTO whatsapp_contacts
                    (contact_id, number, name, push_name, is_my_contact,
                     is_blocked, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows.values(),
            )
        return len(rows)

    def whatsapp_contacts(
        self, limit: int = 256, *, saved_only: bool = True
    ) -> tuple[str, ...]:
        """Cached JIDs usable as WhatsApp status recipients."""
        query = "SELECT contact_id FROM whatsapp_contacts WHERE is_blocked = 0"
        if saved_only:
            query += " AND is_my_contact = 1"
        query += (
            " ORDER BY is_my_contact DESC,"
            " COALESCE(name, push_name, contact_id) COLLATE NOCASE, contact_id"
            " LIMIT ?"
        )
        rows = self._conn.execute(query, (limit,)).fetchall()
        return tuple(row[0] for row in rows)

    def get_offset(self) -> int | None:
        row = self._conn.execute(
            "SELECT value FROM state WHERE key = 'telegram_offset'"
        ).fetchone()
        return int(row[0]) if row else None

    def set_offset(self, offset: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO state (key, value) VALUES ('telegram_offset', ?)",
            (str(offset),),
        )
        self._conn.commit()

    def record_delivery(
        self,
        *,
        url_hash: str,
        chat_id: str,
        message_id: str | None = None,
        error: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO deliveries
                (url_hash, chat_id, message_id, error, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (url_hash, chat_id, message_id, error, _now()),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
