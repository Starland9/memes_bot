"""SQLite state: avoid posting the same news twice."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

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
"""


class Store:
    def __init__(self, path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeError(
                f"DATA_DIR non inscriptible : {path.parent} ({exc})"
            ) from exc
        self._conn = sqlite3.connect(path)
        self._conn.execute(SCHEMA)
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
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
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

    def close(self) -> None:
        self._conn.close()
