"""Command line entry point."""

from __future__ import annotations

import argparse
import logging

from .config import ConfigError, load_settings
from .pipeline import poll_updates, run_once, sync_contacts

logger = logging.getLogger("bot")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Génère un meme à partir de l'actualité et le publie sur Telegram "
            "(et en statut WhatsApp si OpenWA est configuré)."
        )
    )
    parser.add_argument("--once", action="store_true", help="exécute un seul cycle (défaut)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="génère l'image sans publier (écrit dans DATA_DIR/out)",
    )
    parser.add_argument(
        "--poll-updates",
        action="store_true",
        help="relève les /start et /stop des abonnés puis quitte",
    )
    parser.add_argument(
        "--sync-contacts",
        action="store_true",
        help="met en cache les contacts WhatsApp via OpenWA puis quitte",
    )
    parser.add_argument("--log-level", default="INFO", help="niveau de log (défaut : INFO)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        settings = load_settings(dry_run=args.dry_run or None)
    except ConfigError as exc:
        logger.error("%s", exc)
        return 2

    if args.sync_contacts:
        try:
            result = sync_contacts(settings)
        except ConfigError as exc:
            logger.error("%s", exc)
            return 2
        except Exception:
            logger.exception("Échec de la synchronisation des contacts")
            return 2
        logger.info("%s : %s", result.status, result.detail)
        return 0

    if args.poll_updates:
        try:
            result = poll_updates(settings)
        except Exception:
            logger.exception("Échec de la relève des abonnés")
            return 2
        logger.info("%s : %s", result.status, result.detail)
        return 0

    if settings.dry_run:
        logger.info(
            "Mode dry-run : aucune publication Telegram ni statut WhatsApp"
        )

    try:
        result = run_once(settings)
    except Exception:
        logger.exception("Échec du cycle")
        return 2

    logger.info("%s : %s", result.status, result.detail)
    return 0 if result.status in {"posted", "dry_run"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
