import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bot.config import load_settings
from bot.llm import MemePlan
from bot.news import NewsItem
from bot.pipeline import poll_updates, run_once, url_hash
from bot.store import Store
from bot.telegram import TelegramError
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
    def _settings(self, tmp: str, dry_run: bool = True, chat_id: str = "42"):
        return load_settings(
            env={
                "DEEPSEEK_API_KEY": "key",
                "TELEGRAM_BOT_TOKEN": "token",
                "TELEGRAM_CHAT_ID": chat_id,
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
            sent: list[tuple[str, bytes, str]] = []

            def publisher(chat_id: str, image: bytes, caption: str) -> dict:
                sent.append((chat_id, image, caption))
                return {"message_id": 7}

            result = run_once(
                settings,
                store=store,
                update_fetcher=lambda offset: [],
                news_fetcher=lambda: [SAFE_ITEM],
                template_fetcher=lambda: TEMPLATES,
                generator=lambda item, templates, recent: MemePlan(
                    "drake", ("Avant", "Après"), "Légende"
                ),
                image_fetcher=lambda url: b"image",
                publisher=publisher,
            )

            self.assertEqual(result.status, "posted")
            self.assertEqual(sent, [("42", b"image", "Légende")])
            self.assertIn("1 destinataire", result.detail)
            store.close()

    def test_broadcasts_to_each_subscriber(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self._settings(tmp, dry_run=False, chat_id="")
            store = Store(Path(tmp) / "bot.db")
            store.add_subscriber("111")
            store.add_subscriber("222")
            sent: list[tuple[str, bytes, str]] = []

            def publisher(chat_id: str, image: bytes, caption: str) -> dict:
                sent.append((chat_id, image, caption))
                return {"message_id": len(sent)}

            result = run_once(
                settings,
                store=store,
                update_fetcher=lambda offset: [],
                news_fetcher=lambda: [SAFE_ITEM],
                template_fetcher=lambda: TEMPLATES,
                generator=lambda item, templates, recent: MemePlan(
                    "drake", ("Avant", "Après"), "Légende"
                ),
                image_fetcher=lambda url: b"image",
                publisher=publisher,
            )

            self.assertEqual(result.status, "posted")
            self.assertEqual([row[0] for row in sent], ["111", "222"])
            self.assertIn("2 destinataire", result.detail)
            store.close()

    def test_registers_subscribers_from_updates_before_broadcasting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self._settings(tmp, dry_run=False, chat_id="")
            store = Store(Path(tmp) / "bot.db")
            sent: list[str] = []
            replies: list[str] = []

            result = run_once(
                settings,
                store=store,
                update_fetcher=lambda offset: [
                    {
                        "update_id": 5,
                        "message": {
                            "chat": {"id": 999, "first_name": "Ada"},
                            "text": "/start",
                        },
                    }
                ],
                notifier=lambda chat_id, text: replies.append(chat_id),
                news_fetcher=lambda: [SAFE_ITEM],
                template_fetcher=lambda: TEMPLATES,
                generator=lambda item, templates, recent: MemePlan(
                    "drake", ("Avant", "Après"), "Légende"
                ),
                image_fetcher=lambda url: b"image",
                publisher=lambda chat_id, image, caption: (
                    sent.append(chat_id) or {"message_id": 1}
                ),
            )

            self.assertEqual(result.status, "posted")
            self.assertEqual(sent, ["999"])
            self.assertEqual(replies, ["999"])
            self.assertEqual(store.get_offset(), 6)
            store.close()

    def test_no_subscriber_skips_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self._settings(tmp, dry_run=False, chat_id="")
            store = Store(Path(tmp) / "bot.db")

            result = run_once(
                settings,
                store=store,
                update_fetcher=lambda offset: [],
                news_fetcher=lambda: self.fail("les actus ne doivent pas être lues"),
                template_fetcher=lambda: self.fail("les templates ne doivent pas être lus"),
                generator=lambda *args: self.fail("le modèle ne doit pas être appelé"),
                image_fetcher=lambda url: b"",
                publisher=lambda *args: self.fail("ne doit pas publier"),
            )

            self.assertEqual(result.status, "nothing")
            self.assertIn("abonné", result.detail)
            store.close()

    def test_poll_updates_registers_subscribers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self._settings(tmp)
            store = Store(Path(tmp) / "bot.db")

            result = poll_updates(
                settings,
                store=store,
                update_fetcher=lambda offset: [
                    {
                        "update_id": 21,
                        "message": {
                            "chat": {"id": 77, "first_name": "Ada"},
                            "text": "/start",
                        },
                    }
                ],
                notifier=lambda chat_id, text: None,
            )

            self.assertEqual(result.status, "updated")
            self.assertEqual(store.subscribers(), ("77",))
            self.assertEqual(store.get_offset(), 22)
            store.close()

    def test_removes_subscriber_blocked_by_the_bot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self._settings(tmp, dry_run=False, chat_id="")
            store = Store(Path(tmp) / "bot.db")
            store.add_subscriber("111")
            store.add_subscriber("222")

            def publisher(chat_id: str, image: bytes, caption: str) -> dict:
                if chat_id == "222":
                    raise TelegramError(
                        "HTTP 403 : Forbidden: bot was blocked by the user"
                    )
                return {"message_id": 1}

            result = run_once(
                settings,
                store=store,
                update_fetcher=lambda offset: [],
                news_fetcher=lambda: [SAFE_ITEM],
                template_fetcher=lambda: TEMPLATES,
                generator=lambda item, templates, recent: MemePlan(
                    "drake", ("Avant", "Après"), "Légende"
                ),
                image_fetcher=lambda url: b"image",
                publisher=publisher,
            )

            self.assertEqual(result.status, "posted")
            self.assertEqual(store.subscribers(), ("111",))
            store.close()


if __name__ == "__main__":
    unittest.main()
