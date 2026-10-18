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

    def test_caches_whatsapp_contacts_for_status_recipients(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "bot.db")
            count = store.replace_whatsapp_contacts(
                [
                    {"id": "111@c.us", "number": "111", "name": "Zoé", "isMyContact": True},
                    {"id": "222@lid", "name": "Ada", "isMyContact": True},
                    {
                        "id": "333@c.us",
                        "name": "Bloqué",
                        "isMyContact": True,
                        "isBlocked": True,
                    },
                    {"id": "444@c.us", "name": "Inconnu", "isMyContact": False},
                    {"id": "999@g.us", "name": "Groupe", "isMyContact": True},
                    {"id": "", "name": "Invalide"},
                ]
            )
            self.assertEqual(count, 4)
            self.assertEqual(
                store.whatsapp_contacts(), ("222@lid", "111@c.us")
            )
            self.assertEqual(
                store.whatsapp_contacts(saved_only=False),
                ("222@lid", "111@c.us", "444@c.us"),
            )

            store.replace_whatsapp_contacts([{"id": "555@c.us", "isMyContact": True}])
            self.assertEqual(store.whatsapp_contacts(), ("555@c.us",))
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
