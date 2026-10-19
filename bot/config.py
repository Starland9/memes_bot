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
    request_timeout: float = 60.0
    openwa_base_url: str = ""
    openwa_api_key: str = ""
    openwa_session_id: str = ""
    openwa_status_recipients: tuple[str, ...] = ()
    openwa_status_use_contacts: bool = False
    openwa_status_chatted_only: bool = False
    openwa_status_chat_days: float = 0.0

    @property
    def openwa_configured(self) -> bool:
        return bool(
            self.openwa_base_url and self.openwa_api_key and self.openwa_session_id
        )


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
    if not dry_run and not env.get("TELEGRAM_BOT_TOKEN"):
        missing.append("TELEGRAM_BOT_TOKEN")
    if missing:
        raise ConfigError(
            "Variables d'environnement manquantes : " + ", ".join(missing)
        )

    openwa = {
        "OPENWA_BASE_URL": env.get("OPENWA_BASE_URL", "").strip(),
        "OPENWA_API_KEY": env.get("OPENWA_API_KEY", "").strip(),
        "OPENWA_SESSION_ID": env.get("OPENWA_SESSION_ID", "").strip(),
    }
    unset_openwa = [name for name, value in openwa.items() if not value]
    if unset_openwa and len(unset_openwa) < len(openwa):
        raise ConfigError(
            "Configuration OpenWA incomplète, variables manquantes : "
            + ", ".join(unset_openwa)
        )

    recipients = tuple(
        jid.strip()
        for jid in env.get("OPENWA_STATUS_RECIPIENTS", "").split(",")
        if jid.strip()
    )

    chatted_only = _env_bool(env.get("OPENWA_STATUS_CHATTED_ONLY"))
    chat_days = float(env.get("OPENWA_STATUS_CHAT_DAYS", "0"))
    # Filtering on chats only makes sense on top of the cached address book.
    use_contacts = (
        _env_bool(env.get("OPENWA_STATUS_USE_CONTACTS"))
        or chatted_only
        or chat_days > 0
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
        request_timeout=float(env.get("REQUEST_TIMEOUT", "60")),
        openwa_base_url=openwa["OPENWA_BASE_URL"].rstrip("/"),
        openwa_api_key=openwa["OPENWA_API_KEY"],
        openwa_session_id=openwa["OPENWA_SESSION_ID"],
        openwa_status_recipients=recipients,
        openwa_status_use_contacts=use_contacts,
        openwa_status_chatted_only=chatted_only,
        openwa_status_chat_days=chat_days,
    )
