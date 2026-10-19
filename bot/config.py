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
    openwa_channel_id: str = ""
    publish_targets: tuple[str, ...] = ("telegram",)

    @property
    def openwa_configured(self) -> bool:
        return bool(
            self.openwa_base_url and self.openwa_api_key and self.openwa_session_id
        )


PUBLISH_TARGETS = ("telegram", "status", "channel")
CHANNEL_ID_SUFFIX = "@newsletter"


def _env_bool(value: str | None, default: bool = False) -> bool:
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_targets(raw: str, openwa_ready: bool) -> tuple[str, ...]:
    if not raw.strip():
        # Historical behaviour: OpenWA configured implies a WhatsApp status post.
        return ("telegram", "status") if openwa_ready else ("telegram",)

    targets = tuple(
        dict.fromkeys(part.strip().lower() for part in raw.split(",") if part.strip())
    )
    if not targets:
        raise ConfigError("PUBLISH_TARGETS est vide")
    unknown = [target for target in targets if target not in PUBLISH_TARGETS]
    if unknown:
        raise ConfigError(
            "PUBLISH_TARGETS contient des cibles inconnues : "
            + ", ".join(unknown)
            + " (valeurs admises : "
            + ", ".join(PUBLISH_TARGETS)
            + ")"
        )
    return targets


def _parse_channel_id(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    base = (
        value[: -len(CHANNEL_ID_SUFFIX)]
        if value.endswith(CHANNEL_ID_SUFFIX)
        else value
    )
    if not (base.isascii() and base.isdigit()):
        raise ConfigError(
            f"OPENWA_CHANNEL_ID invalide : {value} — un id de chaîne est "
            "numérique (ex. 120363000000000000@newsletter). Pour un lien de "
            "partage ou un code d'invitation, lance "
            "`python -m bot --resolve-channel <lien>`."
        )
    return f"{base}{CHANNEL_ID_SUFFIX}"


def load_settings(
    env: dict[str, str] | None = None,
    dry_run: bool | None = None,
    *,
    validate_publish: bool = True,
) -> Settings:
    """Read the environment.

    `validate_publish=False` is for one-off commands (`--resolve-channel`,
    `--sync-contacts`, `--poll-updates`): they must run even when the publishing
    settings are missing or wrong, since one of them computes the channel id.
    """
    env = dict(os.environ if env is None else env)
    if dry_run is None:
        dry_run = _env_bool(env.get("DRY_RUN"))

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
    openwa_ready = not unset_openwa

    if validate_publish:
        targets = _parse_targets(env.get("PUBLISH_TARGETS", ""), openwa_ready)
        channel_id = _parse_channel_id(env.get("OPENWA_CHANNEL_ID", ""))

        if channel_id and not openwa_ready:
            raise ConfigError(
                "OPENWA_CHANNEL_ID nécessite OPENWA_BASE_URL, OPENWA_API_KEY "
                "et OPENWA_SESSION_ID"
            )
        remote = [target for target in targets if target != "telegram"]
        if remote and not openwa_ready:
            raise ConfigError(
                "PUBLISH_TARGETS="
                + ",".join(remote)
                + " nécessite OPENWA_BASE_URL, OPENWA_API_KEY et OPENWA_SESSION_ID"
            )
        if "channel" in targets and not channel_id:
            raise ConfigError(
                "OPENWA_CHANNEL_ID manquant pour publier sur une chaîne WhatsApp"
            )
    else:
        try:
            targets = _parse_targets(env.get("PUBLISH_TARGETS", ""), openwa_ready)
        except ConfigError:
            targets = ("telegram",)
        try:
            channel_id = _parse_channel_id(env.get("OPENWA_CHANNEL_ID", ""))
        except ConfigError:
            channel_id = ""

    missing = ["DEEPSEEK_API_KEY"] if not env.get("DEEPSEEK_API_KEY") else []
    if (
        validate_publish
        and not dry_run
        and "telegram" in targets
        and not env.get("TELEGRAM_BOT_TOKEN")
    ):
        missing.append("TELEGRAM_BOT_TOKEN")
    if missing:
        raise ConfigError(
            "Variables d'environnement manquantes : " + ", ".join(missing)
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
        openwa_channel_id=channel_id,
        publish_targets=targets,
    )
