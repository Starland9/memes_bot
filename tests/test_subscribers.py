import tempfile
import unittest
from pathlib import Path

from bot.store import Store
from bot.subscribers import handle_updates


def update(update_id: int, chat_id: int, text: str) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "chat": {"id": chat_id, "first_name": "Ada", "username": "ada"},
            "text": text,
        },
    }


class HandleUpdatesTest(unittest.TestCase):
    def test_start_then_stop_manage_subscribers_and_offset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "bot.db")
            replies: list[tuple[str, str]] = []

            added, removed = handle_updates(
                [update(10, 42, "/start")],
                store,
                lambda chat_id, text: replies.append((chat_id, text)),
            )

            self.assertEqual((added, removed), (1, 0))
            self.assertEqual(store.subscribers(), ("42",))
            self.assertEqual(store.get_offset(), 11)
            self.assertEqual(replies[0][0], "42")

            added, removed = handle_updates(
                [update(12, 42, "/stop")], store, lambda chat_id, text: None
            )

            self.assertEqual((added, removed), (0, 1))
            self.assertEqual(store.subscribers(), ())
            self.assertEqual(store.get_offset(), 13)
            store.close()

    def test_accepts_bot_suffix_and_ignores_other_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "bot.db")

            added, removed = handle_updates(
                [
                    update(1, 7, "bonjour"),
                    update(2, 8, "/help"),
                    update(3, 9, "/start@MemesBot"),
                ],
                store,
            )

            self.assertEqual((added, removed), (1, 0))
            self.assertEqual(store.subscribers(), ("9",))
            self.assertEqual(store.get_offset(), 4)
            store.close()

    def test_survives_a_failing_notification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "bot.db")

            def notifier(chat_id: str, text: str) -> None:
                raise RuntimeError("Telegram indisponible")

            added, _ = handle_updates([update(4, 5, "/start")], store, notifier)

            self.assertEqual(added, 1)
            self.assertEqual(store.subscribers(), ("5",))
            self.assertEqual(store.get_offset(), 5)
            store.close()


if __name__ == "__main__":
    unittest.main()
