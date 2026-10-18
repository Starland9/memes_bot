import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bot.config import load_settings
from bot.llm import MemePlan
from bot.news import NewsItem
from bot.pipeline import run_once, url_hash
from bot.store import Store
from bot.templates import Template

SAFE_ITEM = NewsItem(
    title="Une puce graphique bat des records",
    url="https://example.com/safe",
    source="Test",
    published=datetime.now(timezone.utc),
)
UNSAFE_ITEM = NewsItem(
    title="Un drame fait plusieurs victimes",
    url="https://example.com/unsafe",
    source="Test",
    published=datetime.now(timezone.utc),
)
TEMPLATES = [Template("drake", "Drakeposting", 2)]


class PipelineTest(unittest.TestCase):
    def _settings(self, tmp: str, dry_run: bool = True):
        return load_settings(
            env={
                "DEEPSEEK_API_KEY": "key",
                "TELEGRAM_BOT_TOKEN": "token",
                "TELEGRAM_CHAT_ID": "42",
                "DATA_DIR": tmp,
            },
            dry_run=dry_run,
        )

    def test_dry_run_writes_image_then_dedupes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self._settings(tmp)
            store = Store(Path(tmp) / "bot.db")
            generated: list[str] = []

            def generator(item, templates, recent):
                generated.append(item.title)
                return MemePlan("drake", ("Avant", "Après"), "Légende")

            kwargs = dict(
                store=store,
                news_fetcher=lambda: [SAFE_ITEM],
                template_fetcher=lambda: TEMPLATES,
                generator=generator,
                image_fetcher=lambda url: b"\x89PNG fake",
                publisher=lambda image, caption: self.fail("ne doit pas publier"),
            )

            first = run_once(settings, **kwargs)
            self.assertEqual(first.status, "dry_run")
            image = Path(tmp) / "out" / f"{url_hash(SAFE_ITEM.url)}.png"
            self.assertTrue(image.exists())
            self.assertEqual(image.read_bytes(), b"\x89PNG fake")

            second = run_once(settings, **kwargs)
            self.assertEqual(second.status, "nothing")
            self.assertEqual(len(generated), 1)
            store.close()

    def test_unsafe_news_is_skipped_without_calling_the_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self._settings(tmp)
            store = Store(Path(tmp) / "bot.db")

            result = run_once(
                settings,
                store=store,
                news_fetcher=lambda: [UNSAFE_ITEM],
                template_fetcher=lambda: TEMPLATES,
                generator=lambda *args: self.fail("le modèle ne doit pas être appelé"),
                image_fetcher=lambda url: b"",
                publisher=lambda image, caption: self.fail("ne doit pas publier"),
            )

            self.assertEqual(result.status, "nothing")
            self.assertTrue(store.is_seen(url_hash(UNSAFE_ITEM.url)))
            store.close()

    def test_publishes_when_not_in_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self._settings(tmp, dry_run=False)
            store = Store(Path(tmp) / "bot.db")
            sent: list[tuple[bytes, str]] = []

            def publisher(image: bytes, caption: str) -> dict:
                sent.append((image, caption))
                return {"message_id": 7}

            result = run_once(
                settings,
                store=store,
                news_fetcher=lambda: [SAFE_ITEM],
                template_fetcher=lambda: TEMPLATES,
                generator=lambda item, templates, recent: MemePlan(
                    "drake", ("Avant", "Après"), "Légende"
                ),
                image_fetcher=lambda url: b"image",
                publisher=publisher,
            )

            self.assertEqual(result.status, "posted")
            self.assertEqual(sent, [(b"image", "Légende")])
            self.assertIn("7", result.detail)
            store.close()


if __name__ == "__main__":
    unittest.main()
