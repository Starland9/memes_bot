import tempfile
import unittest
from pathlib import Path

from bot.store import Store


class StoreTest(unittest.TestCase):
    def test_records_and_dedupes_by_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "bot.db")
            self.assertFalse(store.is_seen("abc"))
            store.record(
                url_hash="abc",
                url="https://example.com/a",
                title="Titre",
                source="Test",
                status="posted",
                template_id="drake",
                lines=("un", "deux"),
                caption="légende",
                message_id="42",
            )
            self.assertTrue(store.is_seen("abc"))
            self.assertEqual(store.recent_templates(), ("drake",))
            store.close()

    def test_survives_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bot.db"
            store = Store(path)
            store.record(
                url_hash="abc",
                url="https://example.com/a",
                title="Titre",
                source="Test",
                status="dry_run",
            )
            store.close()

            reopened = Store(path)
            self.assertTrue(reopened.is_seen("abc"))
            reopened.close()


if __name__ == "__main__":
    unittest.main()
