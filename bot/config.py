"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    """Raised when a required environment variable is missing."""


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str
    memegen_base_url: str
    telegram_bot_token: str
    telegram_chat_id: str
    data_dir: Path
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    dry_run: bool = False
    max_age_hours: float = 8.0
    max_news_items: int = 40
    request_timeout: float = 30.0


def _env_bool(value: str | None, default: bool = False) -> bool:
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings(
    env: dict[str, str] | None = None,
    dry_run: bool | None = None,
) -> Settings:
    env = dict(os.environ if env is None else env)
    if dry_run is None:
        dry_run = _env_bool(env.get("DRY_RUN"))

    missing = ["DEEPSEEK_API_KEY"] if not env.get("DEEPSEEK_API_KEY") else []
    if not dry_run:
        missing += [
            key
            for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
            if not env.get(key)
        ]
    if missing:
        raise ConfigError(
            "Variables d'environnement manquantes : " + ", ".join(missing)
        )

    return Settings(
        deepseek_api_key=env.get("DEEPSEEK_API_KEY", ""),
        memegen_base_url=env.get("MEMEGEN_BASE_URL", "https://api.memegen.link").rstrip("/"),
        telegram_bot_token=env.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=env.get("TELEGRAM_CHAT_ID", ""),
        data_dir=Path(env.get("DATA_DIR", "data")),
        deepseek_base_url=env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        deepseek_model=env.get("DEEPSEEK_MODEL", "deepseek-flash"),
        dry_run=dry_run,
        max_age_hours=float(env.get("MAX_AGE_HOURS", "8")),
        max_news_items=int(env.get("MAX_NEWS_ITEMS", "40")),
        request_timeout=float(env.get("REQUEST_TIMEOUT", "30")),
    )
