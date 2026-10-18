import unittest

from bot.config import ConfigError, load_settings


def _load(**extra: str):
    env = {"DEEPSEEK_API_KEY": "key"}
    env.update(extra)
    return load_settings(env=env, dry_run=True)


class OpenWAConfigTest(unittest.TestCase):
    def test_disabled_by_default(self) -> None:
        settings = _load()
        self.assertFalse(settings.openwa_configured)
        self.assertEqual(settings.openwa_status_recipients, ())

    def test_requires_all_three_settings(self) -> None:
        with self.assertRaisesRegex(ConfigError, "OPENWA_API_KEY, OPENWA_SESSION_ID"):
            _load(OPENWA_BASE_URL="http://localhost:2785")

    def test_parses_use_contacts(self) -> None:
        self.assertFalse(_load().openwa_status_use_contacts)
        settings = _load(OPENWA_STATUS_USE_CONTACTS="true")
        self.assertTrue(settings.openwa_status_use_contacts)

    def test_parses_recipients_and_trims_base_url(self) -> None:
        settings = _load(
            OPENWA_BASE_URL="http://localhost:2785/",
            OPENWA_API_KEY="secret",
            OPENWA_SESSION_ID="session-1",
            OPENWA_STATUS_RECIPIENTS="123@c.us, 456@lid ,",
        )
        self.assertTrue(settings.openwa_configured)
        self.assertEqual(settings.openwa_base_url, "http://localhost:2785")
        self.assertEqual(
            settings.openwa_status_recipients, ("123@c.us", "456@lid")
        )


if __name__ == "__main__":
    unittest.main()
